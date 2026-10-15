"""Workday (0.8.13): the public JSON behind a Workday careers site, read like any other ATS.

Written from the endpoint's well-known shape; the live read happens on the maintainer's
machine (reports/081). What these pin: the URL detector, pagination, the per-posting detail
merge, the two date paths (startDate, relative postedOn), apply links on the account's own
host, and that a payload of another shape is reported, never invented."""

from __future__ import annotations

import asyncio
import datetime as dt

import httpx
import pytest

from openhire.ats import get_client
from openhire.ats.base import apply_url_is_trusted, canonical_apply_url, resolve_apply_channel
from openhire.ats.boards import BoardNotSupported, detect_board
from openhire.ats.workday import WorkdayClient, _parts, _relative_to_dt

T = "nvidia.wd5/NVIDIAExternalCareerSite"


def test_tenant_parts_and_urls():
    assert _parts(T) == ("nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite")
    c = WorkdayClient()
    assert c.endpoint(T) == "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
    assert c.careers_url(T) == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
    assert c.detail_endpoint(T, "/job/US-CA/Eng_JR1") == "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/job/US-CA/Eng_JR1"


@pytest.mark.parametrize("url", [
    "https://hsbc.wd3.myworkdayjobs.com/",                 # no site
    "https://hsbc.wd3.myworkdayjobs.com/en-US",            # locale only
    "https://hsbc.wdx.myworkdayjobs.com/External",         # not a cluster
    "https://www.myworkdayjobs.com/External",
    "https://hsbc.wd3.myworkdayjobs.com/wday/cxs/hsbc",    # the API path without a site
])
def test_workday_urls_without_a_site_are_bad_urls(url):
    with pytest.raises(BoardNotSupported) as ei:
        detect_board(url)
    assert ei.value.reason == "bad_url"


def test_detect_accepts_locales_deep_links_and_the_api_path():
    assert detect_board("https://manulife.wd3.myworkdayjobs.com/MFCJH_Jobs") == ("workday", "manulife.wd3/MFCJH_Jobs")
    assert detect_board("https://manulife.wd3.myworkdayjobs.com/zh-CN/MFCJH_Jobs/details/Actuary_JR2") == ("workday", "manulife.wd3/MFCJH_Jobs")
    assert detect_board("https://manulife.wd3.myworkdayjobs.com/wday/cxs/manulife/MFCJH_Jobs/jobs") == ("workday", "manulife.wd3/MFCJH_Jobs")


def test_relative_posted_dates():
    today = dt.date(2026, 10, 15)
    assert _relative_to_dt("Posted Today", today) == dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)
    assert _relative_to_dt("Posted Yesterday", today) == dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc)
    assert _relative_to_dt("Posted 3 Days Ago", today) == dt.datetime(2026, 10, 12, tzinfo=dt.timezone.utc)
    assert _relative_to_dt("Posted 30+ Days Ago", today) is None   # "at least a month" is not a date
    assert _relative_to_dt(None) is None and _relative_to_dt("whenever") is None


# --- a fake Workday ---------------------------------------------------------------------
class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _Jar(dict):
    pass


class _Client:
    """Two list pages (23 postings) and a detail for each; records every call."""

    def __init__(self, total=23, list_status=200, detail_ok=True, shape_ok=True):
        self.calls: list[tuple[str, str]] = []
        self.cookies = _Jar(CALYPSO_CSRF_TOKEN="tok")
        self.total = total
        self.list_status = list_status
        self.detail_ok = detail_ok
        self.shape_ok = shape_ok
        self.list_headers: list[dict] = []

    async def get(self, url, headers=None, **kw):
        self.calls.append(("GET", url))
        if "/wday/cxs/" in url:
            if not self.detail_ok:
                return _Resp(500)
            n = url.rsplit("_JR", 1)[-1]
            return _Resp(200, {"jobPostingInfo": {
                "title": f"Engineer {n}", "jobReqId": f"JR{n}", "jobDescription": f"<p>Build <b>GPUs</b> {n}</p>",
                "location": "Shanghai, China", "additionalLocations": ["Shenzhen, China"] if n == "1" else [],
                "startDate": "2026-10-01", "postedOn": "Posted 14 Days Ago",
                "externalUrl": f"https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/CN/Engineer_JR{n}",
            }})
        return _Resp(200)  # the careers page

    async def post(self, url, json=None, headers=None, **kw):
        self.calls.append(("POST", url))
        self.list_headers.append(dict(headers or {}))
        if self.list_status != 200:
            return _Resp(self.list_status)
        if not self.shape_ok:
            return _Resp(200, {"message": "nope"})
        off = json["offset"]
        rows = [{"title": f"Engineer {i}", "externalPath": f"/job/CN/Engineer_JR{i}",
                 "locationsText": "Shanghai, China", "postedOn": "Posted 14 Days Ago", "bulletFields": [f"JR{i}"]}
                for i in range(off + 1, min(off + 20, self.total) + 1)]
        return _Resp(200, {"total": self.total, "jobPostings": rows})


def test_fetch_pages_merges_details_and_builds_trusted_links():
    fake = _Client()
    res = asyncio.run(WorkdayClient().fetch(fake, T))
    assert res.ok and res.count == 23
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert len(posts) == 2                                   # 20 + 3, then stop on total
    assert fake.list_headers[0]["X-CALYPSO-CSRF-TOKEN"] == "tok"
    first = res.records[0]
    assert first.ats_job_id == "JR1" and first.title == "Engineer 1"
    assert "Build GPUs 1" in first.description_raw
    assert first.location == "Shanghai, China; Shenzhen, China"
    assert first.posted_at == dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)   # startDate wins
    assert first.apply_channel.startswith("https://nvidia.wd5.myworkdayjobs.com/")
    assert "JR1" in first.apply_channel
    assert apply_url_is_trusted(first.apply_channel, "workday")
    assert fake.calls[0] == ("GET", "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite")


def test_missing_detail_falls_back_to_the_list_fields():
    fake = _Client(total=2, detail_ok=False)
    res = asyncio.run(WorkdayClient().fetch(fake, T))
    assert res.ok and res.count == 2
    r = res.records[0]
    assert r.ats_job_id == "JR1" and r.description_raw == "" and r.location == "Shanghai, China"
    assert r.posted_at is not None and r.posted_at.tzinfo is not None   # from the relative "Posted 14 Days Ago"
    assert r.apply_channel == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/CN/Engineer_JR1"


def test_non_200_and_unexpected_shapes_are_reported_not_invented():
    assert asyncio.run(WorkdayClient().fetch(_Client(list_status=404), T)).ok is False
    res = asyncio.run(WorkdayClient().fetch(_Client(shape_ok=False), T))
    assert res.ok is False and res.error == "unexpected payload"
    assert asyncio.run(WorkdayClient().fetch(_Client(), "nvidia.wd5")).ok is False   # no site


def test_apply_resolution_keeps_the_posting_path_and_has_a_fallback():
    url = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/CN/Engineer_JR9"
    r = resolve_apply_channel("workday", T, "JR9", url)
    assert r.url == url and not r.used_fallback
    fallback = canonical_apply_url("workday", T, "JR9")
    assert fallback == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite?q=JR9"
    assert apply_url_is_trusted(fallback, "workday")
    assert not apply_url_is_trusted("https://evil-myworkdayjobs.com/x", "workday")
    assert get_client("workday").vendor == "workday"
