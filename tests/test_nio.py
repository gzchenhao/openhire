"""NIO 蔚来 careers mirror (`www.nio.cn/careers/jobs`) adapter: hermetic, no network.

The fixture is the real page captured on 2026-09-23 with a plain GET, trimmed to five
untouched job records inside the real `__NEXT_DATA__` shape (see the builder note in
reports). The five were picked to cover: the newest engineering title, a title with
trailing whitespace, a sales title, a row whose category is empty, and the oldest row
on the roster (open_date 2021-09-22).

The load-bearing assertions are the ones a description-less source makes easy to get
wrong:
  * `description_raw` is "" and stays "": no JD is invented, and NO skill tag is read
    off the title by any extractor;
  * `posted_at` is the employer's own `open_date` (Beijing-local) and never the crawl time;
  * `apply_channel` is the https form of the employer's Feishu job page, never the
    http:// link the mirror publishes, and it deep-links to the job id;
  * salary stays NULL because the mirror publishes none.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from openhire.ats import all_vendors, apply_url_is_trusted, get_client
from openhire.ats.base import JobRecord, canonical_apply_url, resolve_apply_channel
from openhire.ats.nio import NioClient
from openhire.db import Job, init_db, session_scope
from openhire.db.models import Base, Company
from openhire.pipeline import ingest, rebuild
from openhire.pipeline.extract import (
    DeepSeekExtractor,
    HeuristicExtractor,
    classify_role_family_heuristic,
    extract_skills,
    has_description,
)
from openhire.pipeline.ingest import IngestStats
from openhire.seed import all_candidates

UTC = dt.timezone.utc
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "nio_careers_page.html"
PAGE = FIXTURE.read_text(encoding="utf-8")
# The real 567 answer the same GET got from httpx on 2026-09-23 (curl got the page).
BLOCK_PAGE = (FIXTURES / "nio_edgeone_567.html").read_text(encoding="utf-8")
NEXT_DATA = NioClient.parse_next_data(PAGE)
RAW = NEXT_DATA["props"]["pageProps"]["jobsLists"]["jobs"]
TENANT = "nio"


@pytest.fixture()
def records():
    return NioClient().parse(NEXT_DATA, TENANT)


# --- registration and seed ----------------------------------------------------------------
def test_registered_as_a_vendor():
    assert isinstance(get_client("nio"), NioClient)
    assert get_client("nio").vendor == "nio"


def test_seed_row_is_parked_while_the_edge_blocks_this_client():
    # The candidate is written down (seed/candidates.py, `_NIO`) but commented out: the
    # site's EdgeOne policy answers this crawler with 567 (see the fixture below), and a
    # roster entry would knock on that door every week. Flip this test when it is enabled.
    assert [c for c in all_candidates() if c.vendor == "nio"] == []
    assert "nio" in all_vendors()


# --- parsing ------------------------------------------------------------------------------
def test_fixture_keeps_the_real_next_data_shape():
    assert NEXT_DATA["page"] == "/careers/jobs"
    assert "jobsLists" in NEXT_DATA["props"]["pageProps"]
    assert len(RAW) == 5


def test_parses_every_row(records):
    assert len(records) == len(RAW)
    assert [r.ats_job_id for r in records] == [r["id"] for r in RAW]
    # Titles are stripped: the mirror publishes "资深社媒平台运营 " with a trailing space.
    assert [r.title for r in records] == [r["title"].strip() for r in RAW]
    assert any(r["title"] != r["title"].strip() for r in RAW)


def test_description_is_empty_not_invented(records):
    for r in records:
        assert r.description_raw == ""


def test_location_is_the_published_city(records):
    assert [r.location for r in records] == [r["location"] for r in RAW]
    assert records[0].location == "上海"


def test_salary_is_null_because_none_is_published(records):
    for r in records:
        assert (r.salary_min, r.salary_max, r.salary_currency) == (None, None, None)


def test_remote_hint_defaults_to_unknown(records):
    assert {r.remote_hint for r in records} == {"unknown"}


# --- posted_at ----------------------------------------------------------------------------
def test_posted_at_is_the_employers_open_date_in_beijing_time(records):
    # "2026-09-22 17:03:33" Beijing == 09:03:33Z.
    assert records[0].posted_at == dt.datetime(2026, 9, 22, 9, 3, 33, tzinfo=UTC)
    # The oldest row on the roster keeps its real 2021 date rather than the crawl time.
    assert records[-1].posted_at == dt.datetime(2021, 9, 22, 8, 0, 30, tzinfo=UTC)


def test_missing_or_garbage_open_date_becomes_null():
    assert NioClient._date(None) is None
    assert NioClient._date("") is None
    assert NioClient._date("not a date") is None
    assert NioClient._date("0001-01-01 00:00:00") is None


# --- apply_channel ------------------------------------------------------------------------
def test_apply_channel_is_https_feishu_page_deep_linking_the_job(records):
    for r, raw in zip(records, RAW):
        assert raw["url"].startswith("http://nio.jobs.feishu.cn/")  # what the mirror says
        assert r.apply_channel == (
            f"https://nio.jobs.feishu.cn/index/position/detail/{raw['id']}"
        )
        assert apply_url_is_trusted(r.apply_channel, vendor="nio")


def test_plain_http_vendor_url_falls_back_to_canonical_https():
    res = resolve_apply_channel(
        "nio", TENANT, "42", "http://nio.jobs.feishu.cn/index/position/detail/42"
    )
    assert res.url == canonical_apply_url("nio", TENANT, "42")
    assert res.used_fallback is True
    assert res.is_embed is False  # same host, only the scheme was wrong
    # Already canonical: trusted as-is, and re-resolving is idempotent.
    again = resolve_apply_channel("nio", TENANT, "42", res.url)
    assert again.url == res.url and again.used_fallback is False


@pytest.mark.parametrize("url", [
    "https://nio.jobs.feishu.cn/index/position/detail/7688282539764582666",
    "https://www.nio.cn/careers/jobs",
])
def test_nio_hosts_are_trusted(url):
    assert apply_url_is_trusted(url) is True


@pytest.mark.parametrize("url", [
    "http://nio.jobs.feishu.cn/index/position/detail/7688282539764582666",
    "https://evil.jobs.feishu.cn/index/position/detail/1",
    "https://nio.jobs.feishu.cn.attacker.net/x",
])
def test_lookalike_or_plain_http_is_not_trusted(url):
    assert apply_url_is_trusted(url) is False


# --- fetch ---------------------------------------------------------------------------------
class _PageTransport(httpx.AsyncBaseTransport):
    def __init__(self, status: int = 200, body: str = PAGE):
        self.status, self.body = status, body
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        return httpx.Response(self.status, text=self.body)


async def _fetch(transport, tenant=TENANT):
    async with httpx.AsyncClient(transport=transport) as client:
        return await NioClient().fetch(client, tenant)


@pytest.mark.asyncio
async def test_fetch_is_one_get_of_the_careers_page():
    transport = _PageTransport()
    result = await _fetch(transport)
    assert result.ok and result.status == 200
    assert result.count == len(RAW)
    assert len(transport.requests) == 1
    req = transport.requests[0]
    assert req.method == "GET"
    assert str(req.url) == "https://www.nio.cn/careers/jobs"
    assert req.headers["accept"].startswith("text/html")


@pytest.mark.asyncio
async def test_fetch_rejects_non_200():
    result = await _fetch(_PageTransport(status=503, body="nope"))
    assert result.ok is False and result.status == 503


@pytest.mark.asyncio
async def test_edge_block_is_named_and_not_retried():
    """A 567 from Tencent EdgeOne is the site owner's security policy. The adapter says
    so in the error, makes exactly one request, and stores nothing."""
    transport = _PageTransport(status=567, body=BLOCK_PAGE)
    result = await _fetch(transport)
    assert result.ok is False and result.status == 567 and result.count == 0
    assert "security policy" in result.error and "EdgeOne" in result.error
    assert "not worked around" in result.error
    assert len(transport.requests) == 1


@pytest.mark.asyncio
async def test_fetch_rejects_a_200_page_without_next_data():
    result = await _fetch(_PageTransport(body="<html><body>maintenance</body></html>"))
    assert result.ok is False and result.status == 200
    assert "__NEXT_DATA__" in (result.error or "")


@pytest.mark.asyncio
async def test_fetch_rejects_a_200_page_whose_roster_is_gone():
    hollow = json.dumps({"props": {"pageProps": {}}, "page": "/careers/jobs"})
    page = f'<html><body><script id="__NEXT_DATA__" type="application/json">{hollow}</script></body></html>'
    result = await _fetch(_PageTransport(body=page))
    assert result.ok is False and result.error == "no jobs array"


@pytest.mark.asyncio
async def test_fetch_rejects_any_other_tenant():
    transport = _PageTransport()
    result = await _fetch(transport, tenant="byd")
    assert result.ok is False and "nio" in (result.error or "")
    assert transport.requests == []  # never touched the network


# --- no skills from a bare title, from any extractor ---------------------------------------
def _title_only(title: str) -> JobRecord:
    return JobRecord(
        ats_job_id="1", title=title, description_raw="", location="上海",
        apply_channel="https://nio.jobs.feishu.cn/index/position/detail/1",
    )


def test_has_description_is_false_for_empty_or_blank():
    assert has_description(_title_only("x")) is False
    assert has_description(JobRecord(ats_job_id="1", title="x", description_raw="  \n",
                                     apply_channel="https://e.co")) is False
    assert has_description(JobRecord(ats_job_id="1", title="x", description_raw="Rust.",
                                     apply_channel="https://e.co")) is True


@pytest.mark.parametrize("title", [
    "信任与安全经理",
    "Trust & Safety Manager",
    "Go-To-Market 经理",          # the bounded `go` pattern matches this on its own
    "Rust工程师",                 # a title that WOULD legitimately match: still no JD
    "AI 芯片加速算法与软件工程师",
])
def test_heuristic_emits_no_skills_for_a_title_only_posting(title):
    res = HeuristicExtractor().extract(_title_only(title))
    assert res.skills == [], (title, res.skills)
    assert res.extractor == "heuristic"
    assert (res.salary_min, res.salary_max, res.salary_currency) == (None, None, None)


def test_the_vocabulary_itself_does_not_see_rust_in_trust():
    # Independent of the guard: even when a title is fed straight to the vocabulary,
    # "信任与安全" has no latin letters and "Trust" is bounded away from "rust".
    assert "rust" not in extract_skills("信任与安全经理")
    assert "rust" not in extract_skills("Trust & Safety Manager")
    # ...but a bare title CAN still trip the vocabulary, which is why the guard exists.
    assert "go" in extract_skills("Go-To-Market 经理")


def test_heuristic_still_reads_skills_when_a_jd_exists():
    rec = JobRecord(ats_job_id="1", title="信任与安全经理", description_raw="熟悉 Rust 与 Kafka。",
                    apply_channel="https://e.co")
    assert {"rust", "kafka"} <= set(HeuristicExtractor().extract(rec).skills)


class _NeverCall(DeepSeekExtractor):
    def __init__(self):
        super().__init__("key", "https://llm.invalid", "model")

    def _call(self, payload):  # pragma: no cover - the whole point is that it is not reached
        raise AssertionError("an LLM must not be asked to extract skills from a bare title")


def test_llm_extractor_never_sees_a_title_only_posting():
    res, pin, pout = _NeverCall().extract_with_usage(_title_only("信任与安全经理"))
    assert res.skills == [] and (pin, pout) == (0, 0)
    assert res.extractor == "heuristic"  # provenance says who answered
    assert _NeverCall().extract(_title_only("Rust工程师")).skills == []


def test_role_family_is_a_reading_of_the_title_and_is_unchanged():
    # role_family is defined as title-derived, so a title-only row may carry one. That is
    # a classification of what the employer wrote, not a manufactured requirement.
    assert classify_role_family_heuristic("AI 芯片加速算法与软件工程师", "") == "engineering"
    assert classify_role_family_heuristic("", "") is None


# --- ingest end to end --------------------------------------------------------------------
NOW = dt.datetime(2026, 9, 23, tzinfo=UTC)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = Session(engine, future=True)
    s.add(Company(id="nio", name="蔚来 NIO", ats_vendor="nio", ats_tenant="nio",
                  careers_url="https://www.nio.cn/careers/jobs", verified=False))
    s.commit()
    return s


def test_ingest_stores_empty_jd_no_skills_and_the_real_date(records):
    s = _session()
    company = s.get(Company, "nio")
    result = get_client("nio").parse(NEXT_DATA, TENANT)
    stats = IngestStats()
    ingest.ingest_company(
        s, company, ingest.FetchResult(ok=True, status=200, records=result),
        HeuristicExtractor(), stats, now=NOW,
    )
    s.commit()
    rows = list(s.execute(select(Job).order_by(Job.id)).scalars())
    assert stats.jobs_new == len(RAW) == len(rows)
    for job in rows:
        assert job.description_raw == ""
        assert job.skills == []
        assert job.extraction_source == "heuristic"
        assert job.salary_min is None and job.salary_max is None
        assert job.posted_at is not None and job.posted_at < NOW
        assert job.apply_channel.startswith("https://nio.jobs.feishu.cn/")
    # ghost_score ages off open_date: the 2021 row is far staler than the 2026 one.
    by_id = {j.id.split(":", 1)[1]: j for j in rows}
    assert by_id[RAW[-1]["id"]].ghost_score > by_id[RAW[0]["id"]].ghost_score


class _FakeDeepSeek:
    def __init__(self):
        self.seen: list[str] = []

    name = "deepseek"

    def extract_with_usage(self, rec):
        self.seen.append(rec.ats_job_id)
        from openhire.pipeline.extract import ExtractionResult
        return ExtractionResult(skills=["cuda"], remote_policy="onsite",
                                extractor="deepseek"), 100, 10


def test_monthly_llm_pass_skips_rows_with_no_jd(monkeypatch):
    init_db()
    fake = _FakeDeepSeek()
    monkeypatch.setattr(rebuild, "make_deepseek_extractor", lambda: fake)
    with session_scope() as s:
        for t in (Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="nio", name="蔚来 NIO", ats_vendor="nio", ats_tenant="nio",
                      careers_url="u", last_crawled_at=NOW))
        common = dict(company_id="nio", remote_policy="unknown", first_seen_at=NOW,
                      verified_at=NOW, source="ats_public_api", ghost_score=0.0,
                      extraction_source="heuristic",
                      apply_channel="https://nio.jobs.feishu.cn/index/position/detail/1")
        s.add(Job(id="nio:bare", title="信任与安全经理", description_raw="", skills=[],
                  content_hash="h1", **common))
        s.add(Job(id="nio:blank", title="Rust工程师", description_raw="  \n", skills=[],
                  content_hash="h2", **common))
        s.add(Job(id="nio:jd", title="Rust工程师", description_raw="熟悉 Rust。",
                  skills=["rust"], content_hash="h3", **common))
    stats = rebuild.rebuild_extraction(batch_size=10, workers=1, ceiling_cny=999)
    assert stats.total_target == 1 and stats.updated == 1
    assert fake.seen == ["jd"]
    with session_scope() as s:
        assert s.get(Job, "nio:bare").skills == []
        assert s.get(Job, "nio:bare").extraction_source == "heuristic"
        assert s.get(Job, "nio:jd").extraction_source == "deepseek"
        assert s.scalar(select(func.count()).select_from(Job)
                        .where(Job.extraction_source == "deepseek")) == 1
