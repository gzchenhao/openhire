"""posted_within_days and hiring_trend (0.8.38, reports/114): a Zhihu commenter filters to
postings "发布至今14天内"; seekers afraid of rescinded offers want to see a company growing or
shrinking before they sign. Both read the index at query time and never touch ranking."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError

NOW = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="waymo", name="Waymo", ats_vendor="greenhouse", ats_tenant="waymo"))
        for i, (posted, delisted) in enumerate([(3, None), (10, None), (20, None), (45, None), (50, 5)]):
            s.add(Job(id=f"waymo:{i}", company_id="waymo", title="Engineer", description_raw="",
                      source="ats_public_api", first_seen_at=NOW - dt.timedelta(days=posted), verified_at=NOW,
                      posted_at=NOW - dt.timedelta(days=posted),
                      delisted_at=(NOW - dt.timedelta(days=delisted)) if delisted else None,
                      skills=[], location="SF", content_hash=f"h{i}", ghost_score=0.0, remote_policy="onsite",
                      apply_channel="https://boards.greenhouse.io/waymo/jobs/1"))
        s.flush()
        yield s


def test_posted_within_days_filters_by_the_employer_date(session):
    ids = [r["job_id"] for r in service.search_jobs(session, posted_within_days=14, now=NOW)]
    assert sorted(ids) == ["waymo:0", "waymo:1"]
    assert len(service.search_jobs(session, now=NOW)) == 4          # the delisted one is never live
    w = service.watch_intent(session, "#fresh-k2p7x8q1z9", {"posted_within_days": 14}, now=NOW)
    assert w["matching_now"] == 2
    out = service.diagnose_empty_search(session, posted_within_days=14, title=["nothing-like-this"])
    assert out["filters_applied"]["posted_within_days"] == 14


@pytest.mark.parametrize("bad", [0, -3, 400, "abc"])
def test_posted_within_days_refuses_nonsense(session, bad):
    with pytest.raises(OpenHireError):
        service.search_jobs(session, posted_within_days=bad, now=NOW)


def test_hiring_trend_counts_two_windows_and_takedowns(session):
    t = service.get_company_info(session, "waymo", now=NOW)["hiring_trend"]
    assert (t["new_last_30d"], t["new_prior_30d"], t["delisted_last_30d"]) == (3, 2, 1)
    assert "不是对公司前景的判断" in t["in_words"]["zh"] and "not a forecast" in t["in_words"]["en"]


def test_mcp_search_schema_has_posted_within_days():
    import asyncio
    from openhire.mcp_server import mcp
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert "posted_within_days" in tools["search_jobs"].inputSchema["properties"]
