"""0.8.6: Workable and SmartRecruiters adapters (reports/075).

Both are written from the vendors' documented public endpoints; the cloud session that
wrote them cannot reach either host, so these tests pin the parsing contract on fixture
payloads and the fetch logic on a mock transport. The first live read runs on the
maintainer's machine through the local task queue.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json

import httpx
import pytest

from openhire import service
from openhire.ats import all_vendors, apply_url_is_trusted, get_client
from openhire.ats.base import FetchResult, canonical_apply_url
from openhire.ats.boards import BoardNotSupported, SUPPORTED, detect_board
from openhire.ats.smartrecruiters import SmartRecruitersClient
from openhire.ats.workable import WorkableClient, _date_to_dt

NOW = dt.datetime(2026, 10, 12, 8, 0, tzinfo=dt.timezone.utc)


@pytest.fixture()
def session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from openhire.db.models import Base

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s

WORKABLE_PAYLOAD = {
    "name": "Robotec.ai",
    "jobs": [
        {
            "title": "Robotics Simulation Engineer",
            "shortcode": "AB12CD3",
            "code": "",
            "employment_type": "Full-time",
            "telecommuting": False,
            "department": "Robotics",
            "url": "https://apply.workable.com/robotec-ai/j/AB12CD3/",
            "application_url": "https://apply.workable.com/robotec-ai/j/AB12CD3/apply/",
            "published_on": "2026-09-10",
            "country": "Poland",
            "city": "Warsaw",
            "state": "Mazowieckie",
            "locations": [{"country": "Poland", "countryCode": "PL", "city": "Warsaw", "region": "Mazowieckie"}],
            "description": "<p>Build <b>simulation</b> tools.</p>",
            "requirements": "<ul><li>ROS 2</li><li>C++</li></ul>",
            "benefits": "<p>Remote-friendly.</p>",
        },
        {
            "title": "Remote Backend Developer",
            "shortcode": "ZZ99YY8",
            "telecommuting": True,
            "url": "https://apply.workable.com/robotec-ai/j/ZZ99YY8/",
            "published_on": "2026-10-01T09:30:00Z",
            "city": "", "state": "", "country": "",
            "description": "",
        },
        {"title": "no id, skipped", "published_on": "2026-10-02"},
    ],
}


def test_workable_parse_reads_shortcode_dates_locations_and_remote():
    recs = WorkableClient().parse(WORKABLE_PAYLOAD, "robotec-ai")
    assert [r.ats_job_id for r in recs] == ["AB12CD3", "ZZ99YY8"]
    first, second = recs
    assert first.title == "Robotics Simulation Engineer"
    assert "simulation tools" in first.description_raw and "ROS 2" in first.description_raw and "Remote-friendly" in first.description_raw
    assert first.location == "Warsaw, Mazowieckie, Poland" and first.remote_hint == "unknown"
    # A bare date becomes that day at 00:00 UTC, aware, so days_open can be computed.
    assert first.posted_at == dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc) and first.updated_at is None
    # The vendor's own apply URL is on the canonical host and carries the shortcode: trusted as is.
    assert first.apply_channel == "https://apply.workable.com/robotec-ai/j/AB12CD3/apply/"
    assert apply_url_is_trusted(first.apply_channel, "workable")
    assert second.remote_hint == "remote" and second.location is None
    assert second.posted_at == dt.datetime(2026, 10, 1, 9, 30, tzinfo=dt.timezone.utc)
    assert canonical_apply_url("workable", "robotec-ai", "AB12CD3") == "https://apply.workable.com/robotec-ai/j/AB12CD3/"
    assert _date_to_dt("not a date") is None and _date_to_dt(None) is None


def test_workable_lists_a_job_once_per_city_and_one_row_keeps_every_city():
    # Live 2026-10-12: Flexion's "AI Research Engineer" came back twice with the same shortcode,
    # once for Zürich and once for San Francisco. One job, one primary key, both cities.
    payload = {"name": "Flexion", "jobs": [
        {"title": "AI Research Engineer", "shortcode": "CC3F9AC458", "published_on": "2026-10-08",
         "locations": [{"city": "Zürich", "region": "Zurich", "country": "Switzerland"}], "description": "<p>x</p>"},
        {"title": "AI Research Engineer", "shortcode": "CC3F9AC458", "published_on": "2026-10-08",
         "locations": [{"city": "San Francisco", "region": "California", "country": "United States"}], "description": "<p>x</p>"},
        {"title": "Solo", "shortcode": "0001", "published_on": "2026-10-08",
         "locations": [{"city": "Palo Alto", "country": "United States"}, {"city": "Petaluma", "country": "United States"}]},
    ]}
    recs = WorkableClient().parse(payload, "flexion-robotics")
    assert [r.ats_job_id for r in recs] == ["CC3F9AC458", "0001"]
    assert recs[0].location == "Zürich, Zurich, Switzerland; San Francisco, California, United States"
    assert recs[1].location == "Palo Alto, United States; Petaluma, United States"


def test_workable_fetch_validates_the_tenant_like_every_other_vendor():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "robotec-ai" in request.url.path:
            return httpx.Response(200, json=WORKABLE_PAYLOAD)
        return httpx.Response(404, json={"error": "not found"})

    async def go(tenant):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await WorkableClient().fetch(client, tenant)

    ok = asyncio.run(go("robotec-ai"))
    assert ok.ok and ok.status == 200 and ok.count == 2
    assert calls[0] == "https://apply.workable.com/api/v1/widget/accounts/robotec-ai?details=true"
    missing = asyncio.run(go("nobody"))
    assert missing.ok is False and missing.status == 404 and missing.records == []


SR_LIST_PAGE1 = {
    "offset": 0, "limit": 100, "totalFound": 101,
    "content": [
        {
            "id": f"7439{n:05d}", "name": f"ADAS Engineer {n}", "uuid": "u",
            "releasedDate": "2026-09-01T10:00:00.000Z",
            "location": {"city": "Stuttgart", "region": "BW", "country": "de", "remote": False, "hybrid": n % 2 == 0,
                         "fullLocation": "Stuttgart, BW, Germany"},
            "ref": f"https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/7439{n:05d}",
        }
        for n in range(100)
    ],
}
SR_LIST_PAGE2 = {
    "offset": 100, "limit": 100, "totalFound": 101,
    "content": [{
        "id": "999", "name": "Remote Perception Lead", "releasedDate": "2026-10-05T08:00:00.000Z",
        "location": {"city": "", "region": "", "country": "us", "remote": True},
    }],
}


def _sr_detail(pid: str) -> dict:
    return {
        "id": pid,
        "applyUrl": f"https://jobs.smartrecruiters.com/BoschGroup/{pid}-adas-engineer",
        "postingUrl": f"https://jobs.smartrecruiters.com/BoschGroup/{pid}?trid=x",
        "jobAd": {"sections": {
            "companyDescription": {"title": "Company Description", "text": "<p>Bosch.</p>"},
            "jobDescription": {"title": "Job Description", "text": "<p>Own the <b>sensor fusion</b> stack.</p>"},
            "qualifications": {"title": "Qualifications", "text": "<ul><li>C++</li></ul>"},
        }},
    }


def test_smartrecruiters_fetch_pages_the_list_and_merges_one_bounded_detail_per_posting():
    list_calls, detail_calls = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/postings"):
            list_calls.append(request.url.params.get("offset"))
            page = SR_LIST_PAGE1 if request.url.params.get("offset") == "0" else SR_LIST_PAGE2
            return httpx.Response(200, json=page)
        pid = path.rsplit("/", 1)[-1]
        detail_calls.append(pid)
        if pid == "999":
            return httpx.Response(500, text="boom")  # one detail failing never kills the read
        return httpx.Response(200, json=_sr_detail(pid))

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await SmartRecruitersClient().fetch(client, "BoschGroup")

    res = asyncio.run(go())
    assert res.ok and res.count == 101
    assert list_calls == ["0", "100"] and len(detail_calls) == 101
    first = res.records[0]
    assert first.title == "ADAS Engineer 0" and "sensor fusion" in first.description_raw and "C++" in first.description_raw
    assert first.location == "Stuttgart, BW, Germany" and first.remote_hint == "hybrid"
    assert first.posted_at == dt.datetime(2026, 9, 1, 10, 0, tzinfo=dt.timezone.utc) and first.updated_at is None
    assert first.apply_channel == "https://jobs.smartrecruiters.com/BoschGroup/743900000-adas-engineer"
    assert apply_url_is_trusted(first.apply_channel, "smartrecruiters")
    last = res.records[-1]
    assert last.ats_job_id == "999" and last.description_raw == "" and last.remote_hint == "remote"
    assert last.location == "us"
    # No vendor URL for the one whose detail failed: the canonical posting page is built.
    assert last.apply_channel == canonical_apply_url("smartrecruiters", "BoschGroup", "999")


def test_smartrecruiters_tenant_without_a_public_feed_is_not_a_tenant():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Company not found"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await SmartRecruitersClient().fetch(client, "nobody")

    res = asyncio.run(go())
    assert res.ok is False and res.status == 404 and res.records == []


def test_both_vendors_are_registered_and_named_as_supported_boards():
    assert "workable" in all_vendors() and "smartrecruiters" in all_vendors()
    assert isinstance(get_client("workable"), WorkableClient)
    assert isinstance(get_client("smartrecruiters"), SmartRecruitersClient)
    assert "Workable" in SUPPORTED and "SmartRecruiters" in SUPPORTED


@pytest.mark.parametrize("url,expected", [
    ("https://apply.workable.com/robotec-ai/", ("workable", "robotec-ai")),
    ("https://apply.workable.com/robotec-ai/j/AB12CD3/", ("workable", "robotec-ai")),
    ("https://apply.workable.com/api/v1/widget/accounts/robotec-ai?details=true", ("workable", "robotec-ai")),
    ("https://robotec-ai.workable.com/", ("workable", "robotec-ai")),
    ("https://jobs.smartrecruiters.com/BoschGroup", ("smartrecruiters", "BoschGroup")),
    ("https://jobs.smartrecruiters.com/BoschGroup/743900000-adas-engineer", ("smartrecruiters", "BoschGroup")),
    ("https://careers.smartrecruiters.com/BoschGroup", ("smartrecruiters", "BoschGroup")),
    ("https://api.smartrecruiters.com/v1/companies/BoschGroup/postings", ("smartrecruiters", "BoschGroup")),
])
def test_detect_board_reads_workable_and_smartrecruiters_urls(url, expected):
    assert detect_board(url) == expected


@pytest.mark.parametrize("url", [
    "https://www.workable.com/",
    "https://jobs.workable.com/view/abc",
    "https://apply.workable.com/",
    "https://api.smartrecruiters.com/v1/postings",
])
def test_vendor_home_pages_are_not_tenants(url):
    with pytest.raises(BoardNotSupported) as ei:
        detect_board(url)
    assert ei.value.reason == "bad_url"


def test_read_board_reads_a_workable_board_live(session):
    service._BOARD_CACHE.clear()
    records = WorkableClient().parse(WORKABLE_PAYLOAD, "robotec-ai")
    seen = []

    def fake_fetch(vendor, tenant):
        seen.append((vendor, tenant))
        return FetchResult(ok=True, status=200, records=records)

    res = service.read_board(session, url="https://apply.workable.com/robotec-ai/", now=NOW, fetch=fake_fetch)
    assert seen == [("workable", "robotec-ai")] and res["ok"] and res["count_on_board"] == 2
    dated = next(p for p in res["postings"] if p["title"] == "Robotics Simulation Engineer")
    assert dated["datePosted"] == "2026-09-10" and dated["days_open"] == 32 and dated["date_signal"] == "ats_reported"
    assert dated["apply_channel"].startswith("https://apply.workable.com/robotec-ai/")
