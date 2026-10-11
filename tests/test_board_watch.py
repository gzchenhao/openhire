"""Board watches (reports/070): watch_intent with board_url, check_watches reads it live.

Why: a seeker's employer is often outside the index. read_board gave a one-off look; a watch
makes it a standing one. The assertions: the first pull is the baseline, later pulls report
what appeared and what disappeared, a board that does not answer never marks anything
closed, and the filters that mean nothing on a live read are refused at registration.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.ats import FetchResult, JobRecord
from openhire.db.models import Base
from openhire.errors import OpenHireError

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 11, tzinfo=UTC)
FP = "#board-watch-x8q1-k2p7"


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s


def _rec(i: int, title: str, loc: str = "Hong Kong") -> JobRecord:
    return JobRecord(ats_job_id=str(i), title=title, description_raw="x", location=loc,
                     apply_channel=f"https://jobs.ashbyhq.com/uipath/{i}/application",
                     posted_at=T0 - dt.timedelta(days=i))


def test_board_watch_reports_what_appeared_and_what_disappeared(session, monkeypatch):
    live = {"now": [_rec(1, "Partner Sales Manager"), _rec(2, "Software Engineer", "Bengaluru"), _rec(3, "Talent Acquisition Partner")]}
    monkeypatch.setattr(service, "_fetch_board", lambda v, t: FetchResult(ok=True, status=200, records=live["now"]))
    service._BOARD_CACHE.clear()
    reg = service.watch_intent(session, FP, {"board_url": "https://jobs.ashbyhq.com/uipath", "location": "Hong Kong"}, now=T0)
    assert reg["status"] == "active"
    first = service.check_watches(session, FP, now=T0)
    e1 = first["results"][0]
    assert e1["is_first_pull"] and e1["board"] == {"vendor": "ashby", "tenant": "uipath"}
    assert [p["ats_job_id"] for p in e1["new_matches"]] == ["1", "3"] and e1["closed_since_last"] == []
    assert first["new_matches"] == 2
    live["now"] = [_rec(1, "Partner Sales Manager"), _rec(4, "AI Enablement Lead")]
    service._BOARD_CACHE.clear()
    later = service.check_watches(session, FP, now=T0 + dt.timedelta(days=1))
    e2 = later["results"][0]
    assert not e2["is_first_pull"] and [p["ats_job_id"] for p in e2["new_matches"]] == ["4"]
    assert e2["closed_since_last"] == [{"ats_job_id": "3", "title": "Talent Acquisition Partner"}]
    assert later["new_matches"] == 1 and e2["since"] == T0.isoformat()


def test_a_board_that_does_not_answer_keeps_the_remembered_set(session, monkeypatch):
    monkeypatch.setattr(service, "_fetch_board", lambda v, t: FetchResult(ok=True, status=200, records=[_rec(1, "A")]))
    service._BOARD_CACHE.clear()
    service.watch_intent(session, FP, {"board_url": "https://jobs.lever.co/lalamove"}, now=T0)
    service.check_watches(session, FP, now=T0)
    monkeypatch.setattr(service, "_fetch_board", lambda v, t: FetchResult(ok=False, status=503, error="non-200"))
    service._BOARD_CACHE.clear()
    down = service.check_watches(session, FP, now=T0 + dt.timedelta(days=1))["results"][0]
    assert down["board_error"]["status"] == 503 and down["closed_since_last"] == [] and down["new_matches"] == []
    monkeypatch.setattr(service, "_fetch_board", lambda v, t: FetchResult(ok=True, status=200, records=[_rec(1, "A")]))
    service._BOARD_CACHE.clear()
    again = service.check_watches(session, FP, now=T0 + dt.timedelta(days=2))["results"][0]
    assert again["new_matches"] == [] and again["closed_since_last"] == []


def test_board_watch_refuses_index_filters_and_closed_portals(session):
    with pytest.raises(OpenHireError) as ei:
        service.watch_intent(session, FP, {"board_url": "https://jobs.ashbyhq.com/uipath", "skills": ["rust"]}, now=T0)
    assert ei.value.code == "ERR_BAD_QUERY"
    with pytest.raises(OpenHireError) as ei:
        service.watch_intent(session, FP, {"board_url": "https://ponyai.jobs.feishu.cn/ponyai/"}, now=T0)
    assert ei.value.code == "ERR_UNSUPPORTED_BOARD"
