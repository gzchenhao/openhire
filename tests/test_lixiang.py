"""Li Auto (理想汽车, `api-web.lixiang.com`) first-party adapter: hermetic, no network.

The fixture is ONE real capture taken on 2026-09-23: page 1 of the 社招 roster at
page_size=200 (trimmed from 200 items to 3, envelope and counts as served) plus the three
matching `/job/detail` responses, untouched.

The load-bearing assertions are the ones this source makes easy to get wrong:
  * there is NO date anywhere in either response, so posted_at / updated_at are None and
    nothing is backfilled from the crawl time;
  * a row whose detail never arrived has an empty description and NO skills, because the
    title alone must not be mined for tags;
  * the envelope's own error code is a failed fetch, never something to work around;
  * apply_channel is the employer's own page and passes the trust check.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import httpx
import pytest

from openhire.ats import apply_url_is_trusted, get_client
from openhire.ats.base import canonical_apply_url, resolve_apply_channel
from openhire.ats.lixiang import LixiangClient
from openhire.pipeline.extract import HeuristicExtractor
from openhire.seed import all_candidates

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "lixiang_social_page.json"
CAPTURE = json.loads(FIXTURE.read_text(encoding="utf-8"))
LIST = CAPTURE["list"]                       # the raw list envelope
ITEMS = LIST["data"]["items"]
DETAILS = {k: v["data"] for k, v in CAPTURE["details"].items()}  # unwrapped detail data
TENANT = "social"


@pytest.fixture()
def records():
    return LixiangClient().parse({"items": ITEMS, "details": DETAILS}, TENANT)


# --- registry and seed ------------------------------------------------------------
def test_registered_as_a_vendor():
    assert isinstance(get_client("lixiang"), LixiangClient)
    assert get_client("lixiang").vendor == "lixiang"


def test_seeded_once_under_our_own_slug():
    rows = [c for c in all_candidates() if c.vendor == "lixiang"]
    assert [(c.tenant, c.slug) for c in rows] == [("social", "lixiang")]


def test_careers_url_is_the_public_listing_page():
    assert LixiangClient().careers_url(TENANT) == "https://www.lixiang.com/employ/social.html"


# --- the capture itself -------------------------------------------------------------
def test_fixture_is_a_real_envelope_with_no_date_field():
    """The claim this adapter rests on: neither response carries any date."""
    assert LIST["code"] == 0
    assert LIST["data"]["total_count"] == 772 and LIST["data"]["page_size"] == 200
    for row in ITEMS + list(DETAILS.values()):
        assert not any(("date" in k.lower() or "time" in k.lower()) for k in row), row.keys()


# --- parsing --------------------------------------------------------------------
def test_parses_every_row(records):
    assert len(records) == len(ITEMS) == 3
    assert [r.title for r in records] == [j["title"] for j in ITEMS]


def test_five_protocol_fields_present(records):
    for r in records:
        assert r.ats_job_id and r.title
        assert r.description_raw   # 岗位职责 + 任职要求 from the detail call
        assert r.apply_channel.startswith("https://")
        assert r.location


def test_description_is_duties_then_requirements_as_text(records):
    first = records[0]
    raw = DETAILS[first.ats_job_id]
    assert "<p>" in raw["description"] and "<p>" in raw["requirements"]   # served as HTML
    assert "<" not in first.description_raw                                # stored as text
    duties_head = raw["description"].split("</p>")[0].replace("<p>", "").strip()[:12]
    req_head = raw["requirements"].split("</p>")[0].replace("<p>", "").strip()[:12]
    assert first.description_raw.index(duties_head) < first.description_raw.index(req_head)


def test_apply_channel_is_the_employers_own_job_page(records):
    for r, raw in zip(records, ITEMS):
        assert r.ats_job_id == str(raw["id"])
        assert r.apply_channel == f"https://www.lixiang.com/employ/detail/{raw['id']}.html"
        assert apply_url_is_trusted(r.apply_channel)
        assert apply_url_is_trusted(r.apply_channel, vendor="lixiang")


def test_a_self_hosted_looking_url_is_still_replaced_by_the_canonical_page():
    res = resolve_apply_channel("lixiang", TENANT, "275", "https://example.com/careers")
    assert res.used_fallback and res.is_embed
    assert res.url == canonical_apply_url("lixiang", TENANT, "275")
    assert res.url == "https://www.lixiang.com/employ/detail/275.html"


def test_no_date_means_none_never_the_crawl_time(records):
    """The mirror has no posting date; the index must age the row from first_seen_at,
    which the ingest path does when posted_at is None. Inventing one here would be a
    fabricated datePosted, which is worse than a missing one."""
    for r in records:
        assert r.posted_at is None
        assert r.updated_at is None


def test_no_pay_is_published(records):
    for r in records:
        assert (r.salary_min, r.salary_max, r.salary_currency) == (None, None, None)


def test_location_is_the_city_as_served(records):
    assert [r.location for r in records] == [j["location_title"] for j in ITEMS]


def test_remote_hint_defaults_to_unknown(records):
    assert {r.remote_hint for r in records} == {"unknown"}


def test_remote_only_when_explicitly_marked():
    (rec,) = LixiangClient().parse(
        {"items": [{"id": 1, "title": "算法工程师（远程）", "location_title": "北京"}]}, TENANT
    )
    assert rec.remote_hint == "remote"


def test_a_job_without_a_detail_still_becomes_a_record_with_no_description():
    """A failed detail call must not drop the job (that would read as a delisting), and
    the empty description must stay empty rather than be padded from the title."""
    (rec,) = LixiangClient().parse({"items": [dict(ITEMS[0])], "details": {}}, TENANT)
    assert rec.ats_job_id == str(ITEMS[0]["id"])
    assert rec.description_raw == ""


def test_no_skills_are_mined_from_a_title_alone():
    """Guard on the heuristic extractor: 'Python 工程师' with no JD must yield no tags.
    The title still trips the vocabulary, so the extractor must refuse to look."""
    (rec,) = LixiangClient().parse(
        {"items": [{"id": 9, "title": "Python / CUDA 算法工程师", "location_title": "上海"}],
         "details": {}},
        TENANT,
    )
    assert rec.description_raw == ""
    assert HeuristicExtractor().extract(rec).skills == []


# --- the row a client sees ------------------------------------------------------------
def test_search_row_says_the_date_was_not_reported():
    """The row must name the limit: datePosted / days_open are counted from the day we
    first saw it, so `date_signal` is set, exactly as `update_signal` is for updated_at."""
    from openhire import service
    from openhire.db import Company, Job

    now = dt.datetime(2026, 9, 23, tzinfo=dt.timezone.utc)
    first_seen = now - dt.timedelta(days=5)
    company = Company(id="lixiang", name="理想汽车 Li Auto", ats_vendor="lixiang",
                      ats_tenant="social")

    def _job(posted_at):
        return Job(
            id="lixiang:275", company_id="lixiang", title="Engineer", location="北京",
            remote_policy="unknown", skills=["python"], source="ats_public_api",
            first_seen_at=first_seen, posted_at=posted_at, updated_at=None,
            verified_at=now, apply_channel="https://www.lixiang.com/employ/detail/275.html",
            content_hash="h", relist_count=0, ghost_score=0.0,
        )

    undated = service.job_posting(_job(None), company, [], now)
    assert undated["date_signal"] == "not_reported_by_ats"
    assert undated["datePosted"] == first_seen.date().isoformat()
    assert undated["days_open"] == 5
    assert undated["ghost_reason"].startswith("fresh: 5d old")
    assert undated["apply_channel"] == "https://www.lixiang.com/employ/detail/275.html"

    dated = service.job_posting(_job(first_seen - dt.timedelta(days=30)), company, [], now)
    assert "date_signal" not in dated
    assert dated["days_open"] == 35


# --- fetch --------------------------------------------------------------------
class _Mirror(httpx.AsyncBaseTransport):
    """Replays the captured list page and detail responses, paging on `page`."""

    def __init__(self, items, details, *, list_code=0, page_size=None):
        self.items, self.details = items, details
        self.list_code = list_code
        self.calls: list[str] = []
        self.page_size = page_size

    async def handle_async_request(self, request):
        self.calls.append(str(request.url))
        if request.url.path.endswith("/job-page"):
            if self.list_code != 0:
                return httpx.Response(200, json={"code": self.list_code,
                                                 "msg": "没有接口访问权限", "success": False,
                                                 "data": {}})
            page = int(request.url.params["page"])
            size = int(request.url.params["page_size"])
            if self.page_size is not None:
                assert size == self.page_size
            start = (page - 1) * size
            batch = self.items[start:start + size]
            return httpx.Response(200, json={"code": 0, "data": {
                "page": page, "page_size": size, "total_count": len(self.items),
                "total_pages": max(1, -(-len(self.items) // size)), "items": batch}})
        if request.url.path.endswith("/job/detail"):
            job_id = request.url.params["job_id"]
            data = self.details.get(job_id)
            if data is None:
                return httpx.Response(200, json={"code": 100012, "msg": "没有接口访问权限",
                                                 "data": {}})
            return httpx.Response(200, json={"code": 0, "data": data})
        return httpx.Response(404, text="")


async def _fetch(transport, tenant=TENANT):
    async with httpx.AsyncClient(transport=transport) as client:
        return await LixiangClient().fetch(client, tenant), transport


@pytest.mark.asyncio
async def test_fetch_pages_the_roster_then_calls_each_detail(monkeypatch):
    from openhire.ats import lixiang as mod

    monkeypatch.setattr(mod, "_DETAIL_DELAY_SECONDS", 0)
    result, mirror = await _fetch(_Mirror(ITEMS, DETAILS, page_size=200))
    assert result.ok and result.status == 200 and result.count == 3
    list_calls = [c for c in mirror.calls if "/job-page" in c]
    detail_calls = [c for c in mirror.calls if "/job/detail" in c]
    assert len(list_calls) == 1          # 3 rows < page_size: one page, no second request
    assert "page_size=200" in list_calls[0]
    assert len(detail_calls) == 3
    assert all(r.description_raw for r in result.records)


@pytest.mark.asyncio
async def test_fetch_stops_at_total_count(monkeypatch):
    from openhire.ats import lixiang as mod

    monkeypatch.setattr(mod, "_DETAIL_DELAY_SECONDS", 0)
    monkeypatch.setattr(mod, "_PAGE_SIZE", 2)
    result, mirror = await _fetch(_Mirror(ITEMS, DETAILS, page_size=2))
    assert result.ok and result.count == 3
    assert len([c for c in mirror.calls if "/job-page" in c]) == 2   # 2 + 1, then stop


@pytest.mark.asyncio
async def test_fetch_keeps_a_row_whose_detail_failed(monkeypatch):
    from openhire.ats import lixiang as mod

    monkeypatch.setattr(mod, "_DETAIL_DELAY_SECONDS", 0)
    partial = {k: v for k, v in DETAILS.items() if k != str(ITEMS[0]["id"])}
    result, _ = await _fetch(_Mirror(ITEMS, partial))
    assert result.ok and result.count == 3
    missing = next(r for r in result.records if r.ats_job_id == str(ITEMS[0]["id"]))
    assert missing.description_raw == ""


@pytest.mark.asyncio
async def test_fetch_reports_the_api_error_code_and_does_not_retry_around_it():
    result, mirror = await _fetch(_Mirror(ITEMS, DETAILS, list_code=100012))
    assert not result.ok and result.status == 200
    assert "100012" in (result.error or "")
    assert len(mirror.calls) == 1


@pytest.mark.asyncio
async def test_fetch_rejects_non_200():
    transport = httpx.MockTransport(lambda r: httpx.Response(503, text="nope"))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await LixiangClient().fetch(client, TENANT)
    assert result.ok is False


@pytest.mark.asyncio
async def test_campus_board_is_refused():
    """`school` is real (1,044 rows on 2026-09-23) and is campus hiring: not indexed."""
    result, mirror = await _fetch(_Mirror(ITEMS, DETAILS), tenant="school")
    assert not result.ok and "school" in (result.error or "")
    assert mirror.calls == []
