"""`read_board`: any employer on a vendor this index reads, live, nothing stored (reports/069).

A seeker's market is wider than the index's three sectors. The load-bearing assertions:
  * a pasted careers URL resolves to the (vendor, tenant) the adapters take, and a portal we
    cannot read (Feishu, Workday, a job site) is refused with the reason, never scraped;
  * the read is live, filtered like search (location aliases, title synonyms), dated with the
    board's own date or `not_reported_by_ats`, and writes nothing to the index;
  * a repeat within the politeness window is answered from memory; a failed board is not
    cached and is reported as "the board did not answer", never as a fact about the employer;
  * the tool is registered read-only and open-world and names its limits.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire import mcp_server, service
from openhire.ats import FetchResult, JobRecord
from openhire.ats.boards import BoardNotSupported, detect_board
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 11, tzinfo=UTC)


@pytest.mark.parametrize("url,expected", [
    ("https://job-boards.greenhouse.io/aift", ("greenhouse", "aift")),
    ("https://boards.greenhouse.io/mongodb/jobs/123", ("greenhouse", "mongodb")),
    ("https://boards.greenhouse.io/embed/job_board?for=lynxanalytics", ("greenhouse", "lynxanalytics")),
    ("boards-api.greenhouse.io/v1/boards/aift/jobs", ("greenhouse", "aift")),
    ("https://jobs.lever.co/lalamove/", ("lever", "lalamove")),
    ("https://api.lever.co/v0/postings/weride?mode=json", ("lever", "weride")),
    ("https://jobs.ashbyhq.com/uipath/61732b36-c81e", ("ashby", "uipath")),
    ("https://api.ashbyhq.com/posting-api/job-board/airwallex", ("ashby", "airwallex")),
    ("https://app.mokahr.com/apply/yushi/3774#/job/x", ("moka", "yushi/3774")),
    ("https://unitree.zhiye.com/social/jobs", ("beisen", "unitree")),
])
def test_detect_board_reads_vendor_and_tenant_off_the_url(url, expected):
    assert detect_board(url) == expected


@pytest.mark.parametrize("url,reason", [
    ("https://ponyai.jobs.feishu.cn/ponyai/", "closed_portal"),
    ("https://hsbc.wd3.myworkdayjobs.com/x", "closed_portal"),
    ("https://hk.jobsdb.com/x", "closed_portal"),
    ("https://www.hkstp.org/careers", "unsupported_host"),
    ("https://app.mokahr.com/apply/yushi", "bad_url"),
    ("https://www.zhiye.com/", "bad_url"),
    ("", "bad_url"),
])
def test_closed_and_unknown_portals_are_refused_with_the_reason(url, reason):
    with pytest.raises(BoardNotSupported) as ei:
        detect_board(url)
    assert ei.value.reason == reason
    assert ei.value.hint  # a seeker always hears why


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="mongodb", name="MongoDB", ats_vendor="greenhouse", ats_tenant="mongodb",
                      careers_url="https://boards.greenhouse.io/mongodb", last_crawled_at=NOW))
        s.commit()
        yield s


def _records():
    return [
        JobRecord(ats_job_id="1", title="Senior Partner Sales Manager (Agentic AI)", description_raw="Partner ecosystem across Hong Kong.",
                  apply_channel="https://jobs.ashbyhq.com/uipath/1/application", location="Hong Kong", remote_hint="hybrid",
                  posted_at=NOW - dt.timedelta(days=45)),
        JobRecord(ats_job_id="2", title="Software Engineer", description_raw="x",
                  apply_channel="https://jobs.ashbyhq.com/uipath/2/application", location="Bengaluru",
                  posted_at=NOW - dt.timedelta(days=3)),
        JobRecord(ats_job_id="3", title="Talent Acquisition Partner", description_raw="x",
                  apply_channel="https://jobs.ashbyhq.com/uipath/3/application", location="香港", posted_at=None),
    ]


def test_read_board_reads_live_filters_like_search_and_stores_nothing(session):
    calls = []

    def fake_fetch(vendor, tenant):
        calls.append((vendor, tenant))
        return FetchResult(ok=True, status=200, records=_records())

    service._BOARD_CACHE.clear()
    res = service.read_board(session, url="https://jobs.ashbyhq.com/uipath", location="Hong Kong", now=NOW, fetch=fake_fetch)
    assert calls == [("ashby", "uipath")] and res["ok"] and res["stored"] is False and res["in_index"] is None
    assert res["count_on_board"] == 3 and res["total_matching"] == 2 and res["from_cache"] is False
    assert [p["title"] for p in res["postings"]] == ["Senior Partner Sales Manager (Agentic AI)", "Talent Acquisition Partner"]
    dated, undated = res["postings"]
    assert dated["datePosted"] == "2026-08-27" and dated["days_open"] == 45 and dated["date_signal"] == "ats_reported"
    assert dated["apply_channel"].startswith("https://jobs.ashbyhq.com/uipath/")
    assert undated["days_open"] is None and undated["date_signal"] == "not_reported_by_ats"
    assert "skills" not in dated and "ghost_score" not in dated
    assert res["note"].startswith("Read live") and "Nothing about you" in res["privacy"]
    # The HR synonym group reaches "Talent Acquisition" through the title filter, and the
    # second read inside the politeness window comes from memory.
    hr = service.read_board(session, url="https://jobs.ashbyhq.com/uipath", title=["hr"], now=NOW, fetch=fake_fetch)
    assert [p["title"] for p in hr["postings"]] == ["Talent Acquisition Partner"] and hr["from_cache"] is True
    assert len(calls) == 1
    assert session.execute(select(Job)).scalars().first() is None


def test_read_board_knows_an_indexed_employer_and_a_board_that_does_not_answer(session):
    service._BOARD_CACHE.clear()
    res = service.read_board(session, url="https://boards.greenhouse.io/mongodb", now=NOW,
                             fetch=lambda v, t: FetchResult(ok=True, status=200, records=_records()))
    assert res["in_index"] == {"company_id": "mongodb", "name": "MongoDB"} and "search_jobs" in res["hint"]
    down = service.read_board(session, url="https://jobs.lever.co/nobody", now=NOW,
                              fetch=lambda v, t: FetchResult(ok=False, status=404, error="non-200"))
    assert down["ok"] is False and down["status"] == 404 and down["postings"] == []
    assert "nothing about the employer" in down["hint"] and ("lever", "nobody") not in service._BOARD_CACHE
    with pytest.raises(OpenHireError) as ei:
        service.read_board(session, url="https://ponyai.jobs.feishu.cn/ponyai/", now=NOW, fetch=lambda v, t: None)
    assert ei.value.code == "ERR_UNSUPPORTED_BOARD" and "closed_portal" in ei.value.message
    with pytest.raises(OpenHireError) as ei:
        service.read_board(session, url="https://jobs.lever.co/x", limit=0, now=NOW, fetch=lambda v, t: None)
    assert ei.value.code == "ERR_BAD_PAGE"


def test_tool_is_registered_read_only_open_world_and_names_its_limits():
    from mcp.shared.memory import create_connected_server_and_client_session as connect

    async def _tools():
        async with connect(mcp_server.mcp) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    t = asyncio.run(_tools())["read_board"]
    assert t.annotations.readOnlyHint is True and t.annotations.openWorldHint is True
    doc = " ".join((mcp_server.read_board.__doc__ or "").split())
    for phrase in ("whether or not the employer is in this index", "nothing is stored", "ERR_UNSUPPORTED_BOARD",
                   "Feishu", "15 minutes", "Nothing about the user", "never look for another way in"):
        assert phrase in doc, phrase
    assert set(t.inputSchema["properties"]) == {"url", "location", "title", "limit", "offset"}
    assert "read_board" in mcp_server.mcp.instructions


def test_closed_portal_refusal_carries_the_browser_hint(session):
    """0.8.5: the refusal for a signed or JS-only portal tells an assistant with a browser
    tool that it may open the page itself, and that OpenHire reads nothing from it."""
    from openhire.ats.boards import BROWSER_HINT, CLOSED_PORTALS
    assert "浏览器" in BROWSER_HINT and "不入库" in BROWSER_HINT
    for host in ("feishu.cn", "larksuite.com", "myworkdayjobs.com", "successfactors.com", "taleo.net", "icims.com"):
        assert CLOSED_PORTALS[host].endswith(BROWSER_HINT), host
    # Job boards (LinkedIn, JobsDB, BOSS) are not employer systems: no hint, the reason stands alone.
    for host in ("linkedin.com", "jobsdb.com", "zhipin.com"):
        assert BROWSER_HINT not in CLOSED_PORTALS[host], host
    with pytest.raises(service.OpenHireError) as ei:
        service.read_board(session, url="https://ponyai.jobs.feishu.cn/ponyai/", now=NOW, fetch=lambda v, t: None)
    assert ei.value.code == "ERR_UNSUPPORTED_BOARD" and "浏览器" in ei.value.message
