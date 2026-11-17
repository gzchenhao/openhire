"""Hong Kong finance pilot (Howard 2026-11-17, reports/151): the first sector outside engineering,
Hong Kong postings only, never sent to a paid extractor."""
import asyncio
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.ats import FetchResult, JobRecord, base_tenant, fetch_scoped, split_scope
from openhire.ats.base import canonical_apply_url, place_matches, resolve_apply_channel, workday_host
from openhire.db.models import Base, Company, Job
from openhire.seed import sectors
from openhire.seed.candidates import all_candidates


def test_scope_is_ours_and_never_reaches_the_vendor():
    assert split_scope("citi.wd5/2|place=hong kong") == ("citi.wd5/2", "hong kong")
    assert split_scope("anthropic") == ("anthropic", None)
    assert workday_host("citi.wd5/2|place=hong kong") == "citi.wd5.myworkdayjobs.com"
    assert "place" not in canonical_apply_url("greenhouse", "schonfeld|place=hong kong", "1")
    r = resolve_apply_channel("greenhouse", "schonfeld|place=hong kong", "123",
                              "https://boards.greenhouse.io/embed/job_app?for=schonfeld&token=123")
    assert "place" not in r.url and not r.used_fallback


@pytest.mark.parametrize("loc,ok", [
    ("Kowloon  Hong Kong", True), ("Hong Kong, Cheung Kong Center", True), ("Hong Kong, China", True),
    ("Hong Kong Office New; Shanghai Office", True), ("HK - Hong Kong SAR", True), ("香港特别行政区", True),
    ("Singapore", False), ("Chrome, Shanghai", False), (None, False),
])
def test_hong_kong_place(loc, ok):
    assert place_matches("hong kong", loc) is ok


class _Board:
    vendor = "greenhouse"

    def __init__(self):
        self.seen = None

    async def fetch(self, http, tenant):
        self.seen = tenant
        return FetchResult(ok=True, status=200, records=[
            JobRecord(ats_job_id="1", title="Compliance Officer", description_raw="x", apply_channel="https://a/1", location="Hong Kong"),
            JobRecord(ats_job_id="2", title="Compliance Officer", description_raw="x", apply_channel="https://a/2", location="London"),
        ])


def test_fetch_keeps_only_the_place_and_sends_the_bare_tenant():
    board = _Board()
    res = asyncio.run(fetch_scoped(board, None, "schonfeld|place=hong kong"))
    assert board.seen == "schonfeld"
    assert [r.ats_job_id for r in res.records] == ["1"]
    res = asyncio.run(fetch_scoped(_Board(), None, "schonfeld"))
    assert len(res.records) == 2


def test_pilot_rows_are_seeded_scoped_and_labelled_finance():
    rows = [c for c in all_candidates() if sectors.sector_of(c.slug) == sectors.FIN]
    assert len(rows) == 11
    for c in rows:
        assert split_scope(c.tenant)[1] == "hong kong", c
        assert c.company_id and "|" not in c.slug
    assert sectors.zero_extraction("citi-hk") and not sectors.zero_extraction("waymo")
    for word in ("金融", "银行", "finance", "Banking"):
        assert service.check_sector(word) == "finance"


def test_zero_extraction_sector_never_meets_a_paid_extractor():
    from openhire.pipeline import ingest
    from openhire.pipeline.extract import HeuristicExtractor

    class Paid:
        called = 0

        def extract(self, *a, **k):
            Paid.called += 1
            raise AssertionError("a paid extractor was asked")

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    now = dt.datetime(2026, 11, 17, tzinfo=dt.timezone.utc)
    with Session(engine, future=True) as s:
        co = Company(id="citi-hk", name="Citi", ats_vendor="workday", ats_tenant="citi.wd5/2|place=hong kong")
        s.add(co)
        s.flush()
        res = FetchResult(ok=True, status=200, records=[JobRecord(
            ats_job_id="R1", title="Director, Hong Kong Legal", description_raw="Lead the legal team. 10 years.",
            apply_channel="https://citi.wd5.myworkdayjobs.com/2/job/R1", location="Kowloon  Hong Kong")])
        stats = ingest.IngestStats()
        ingest.ingest_company(s, co, res, Paid(), stats, now)
        job = s.get(Job, "citi-hk:R1")
        assert job is not None and job.extraction_source == "heuristic" and Paid.called == 0


def test_rebuild_targets_leave_the_sector_out():
    from openhire.pipeline.rebuild import _PAID_ALLOWED
    assert "citi-hk" in str(_PAID_ALLOWED().compile(compile_kwargs={"literal_binds": True}))


def test_back_office_words_reach_the_functions():
    from openhire.service import expand_title_term
    words = expand_title_term("中后台")
    assert {"compliance", "risk", "operations", "legal", "合规", "风控"} <= set(words)
    assert expand_title_term("compliance") == ["compliance"]
    assert "risk" in expand_title_term("Back Office")
