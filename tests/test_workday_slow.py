"""Workday read slowly (0.8.75, reports/154): the maintainer's "slow Workday down for a week".

From GitHub's runners every Workday board answered 429 or failed fast in the 2026-11-17
refresh. What these pin: a pause between list pages and before each detail read, details one
at a time, a 429 retried once with the identical request after the wait it asks for (capped),
never twice; Workday boards in one crawl one after another; seed validation reads one list page.
"""
from __future__ import annotations

import asyncio

from openhire.ats import workday
from openhire.ats.workday import WorkdayClient
from openhire.pipeline import crawler
from openhire.pipeline.crawler import CompanyRef

T = "nvidia.wd5/NVIDIAExternalCareerSite"


class _Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _Fake:
    def __init__(self, total=23, list_429=0, retry_after=None):
        self.cookies = {}
        self.total = total
        self.list_429 = list_429      # how many list requests answer 429 before a 200
        self.retry_after = retry_after
        self.posts: list[dict] = []
        self.details = 0
        self.in_flight = 0
        self.max_in_flight = 0

    async def get(self, url, headers=None, **kw):
        if "/wday/cxs/" not in url:
            return _Resp(200)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        self.details += 1
        n = url.rsplit("_JR", 1)[-1]
        return _Resp(200, {"jobPostingInfo": {"title": f"E{n}", "jobReqId": f"JR{n}", "location": "Hong Kong"}})

    async def post(self, url, json=None, headers=None, **kw):
        self.posts.append(dict(json))
        if self.list_429 > 0:
            self.list_429 -= 1
            h = {} if self.retry_after is None else {"Retry-After": self.retry_after}
            return _Resp(429, headers=h)
        off = json["offset"]
        rows = [{"title": f"E{i}", "externalPath": f"/job/HK/E_JR{i}", "locationsText": "Hong Kong",
                 "bulletFields": [f"JR{i}"]} for i in range(off + 1, min(off + 20, self.total) + 1)]
        return _Resp(200, {"total": self.total, "jobPostings": rows})


def _record_waits(monkeypatch):
    waits: list[float] = []

    async def rec(seconds):
        waits.append(seconds)

    monkeypatch.setattr(workday, "_pause", rec)
    return waits


def test_pauses_between_pages_and_before_each_detail(monkeypatch):
    waits = _record_waits(monkeypatch)
    fake = _Fake(total=23)
    res = asyncio.run(WorkdayClient().fetch(fake, T))
    assert res.ok and res.count == 23
    assert waits.count(workday._LIST_PAUSE_SECONDS) == 1           # before page 2 only
    assert waits.count(workday._DETAIL_PAUSE_SECONDS) == 23
    assert fake.max_in_flight == 1 and workday._DETAIL_CONCURRENCY == 1
    assert workday._LIST_PAUSE_SECONDS >= 1 and workday._DETAIL_PAUSE_SECONDS >= 0.5


def test_a_429_is_retried_once_with_the_identical_request(monkeypatch):
    waits = _record_waits(monkeypatch)
    fake = _Fake(total=3, list_429=1, retry_after="12")
    res = asyncio.run(WorkdayClient().fetch(fake, T))
    assert res.ok and res.count == 3
    assert fake.posts[0] == fake.posts[1], "the retry is the same request, nothing changed"
    assert waits[0] == 12.0


def test_a_second_429_stops_the_read(monkeypatch):
    _record_waits(monkeypatch)
    fake = _Fake(total=3, list_429=2)
    res = asyncio.run(WorkdayClient().fetch(fake, T))
    assert res.ok is False and res.status == 429
    assert len(fake.posts) == 2, "one identical retry, never a second"


def test_retry_after_is_capped_and_defaults():
    assert workday._retry_after(_Resp(429, headers={"Retry-After": "600"})) == workday._RETRY_AFTER_CAP
    assert workday._retry_after(_Resp(429)) == workday._RETRY_AFTER_DEFAULT
    assert workday._retry_after(_Resp(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})) == workday._RETRY_AFTER_DEFAULT


def test_probe_reads_one_list_page_and_no_details():
    fake = _Fake(total=45)
    res = asyncio.run(WorkdayClient().probe(fake, T))
    assert res.ok and res.count == 20
    assert len(fake.posts) == 1 and fake.details == 0


def test_workday_boards_in_one_crawl_go_one_at_a_time(monkeypatch):
    state = {"now": 0, "max": 0}

    class _Slow:
        vendor = "workday"

        async def fetch(self, http, tenant, place=None):
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
            await asyncio.sleep(0.01)
            state["now"] -= 1
            from openhire.ats.base import FetchResult
            return FetchResult(ok=True, status=200)

    monkeypatch.setattr(crawler, "get_client", lambda vendor: _Slow())
    refs = [CompanyRef(id=f"w{i}", ats_vendor="workday", ats_tenant=f"a{i}.wd1/s", name="x") for i in range(4)]
    out = asyncio.run(crawler.fetch_all(refs, concurrency=5))
    assert len(out) == 4 and state["max"] == 1


def test_seed_validation_probes():
    import inspect

    from openhire.pipeline import seed_runner
    assert "probe=True" in inspect.getsource(seed_runner.seed_companies)


class _DetailRefuses(_Fake):
    """List answers; every detail answers 429."""

    async def get(self, url, headers=None, **kw):
        if "/wday/cxs/" not in url:
            return _Resp(200)
        self.details += 1
        return _Resp(429)


def test_a_detail_refused_twice_stops_all_detail_reads(monkeypatch):
    _record_waits(monkeypatch)
    fake = _DetailRefuses(total=10)
    res = asyncio.run(WorkdayClient().fetch(fake, T))
    assert res.ok and res.count == 10, "the list rows still come back, with list fields only"
    assert fake.details == 2, "one detail and its one identical retry, then nothing more"


def test_details_stop_at_the_time_budget(monkeypatch):
    _record_waits(monkeypatch)
    monkeypatch.setattr(workday, "_DETAIL_BUDGET_SECONDS", -1)
    fake = _Fake(total=5)
    res = asyncio.run(WorkdayClient().fetch(fake, T))
    assert res.ok and res.count == 5 and fake.details == 0
