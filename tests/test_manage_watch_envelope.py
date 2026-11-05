"""0.8.61 (Howard, 2026-11-05, "都做"): manage_watch (list / update / delete a watch) and
search_jobs envelope=true (total, has_more, next_offset). Both were reported two persona nights
running (reports/138, 139)."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError

NOW = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.timezone.utc)
FP = "#mw-k2p7-x8q1-z9"


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme", ats_vendor="lever", ats_tenant="acme", last_crawled_at=NOW))
        for i in range(15):
            when = NOW - dt.timedelta(days=i + 1)
            title = "Senior Perception Engineer" if i % 3 == 0 else "Perception Engineer"
            s.add(Job(id=f"acme:{i}", company_id="acme", title=title, description_raw=title, skills=["perception"],
                      remote_policy="onsite", location="上海", first_seen_at=when, verified_at=NOW, posted_at=when,
                      source="ats_public_api", content_hash=f"h{i}", ghost_score=0.0,
                      apply_channel=f"https://jobs.lever.co/acme/{i}"))
        s.commit()
        yield s


def test_list_update_delete(db):
    w1 = service.watch_intent(db, FP, {"title": ["perception"]}, now=NOW)
    service.check_watches(db, FP, now=NOW)
    listed = service.manage_watch(db, FP, "list")
    assert listed["count"] == 1 and listed["watches"][0]["filters"] == {"title": ["perception"]}
    assert listed["watches"][0]["last_checked_at"]
    up = service.manage_watch(db, FP, "update", watch_id=w1["watch_id"],
                              filters={"title": ["perception"], "seniority": ["senior"]}, now=NOW)
    assert up["replaced_watch_id"] == w1["watch_id"] and up["watch_id"] != w1["watch_id"]
    assert up["matching_now"] == 5 and "替换" in up["what_happens_next"]["zh"]
    assert service.manage_watch(db, FP, "list")["count"] == 1
    first = service.check_watches(db, FP, now=NOW)
    assert first["watches"] == 1 and first["baseline_count"] == 5     # a fresh baseline, one watch only
    gone = service.manage_watch(db, FP, "delete", watch_id=up["watch_id"])
    assert gone["deleted"] == up["watch_id"] and gone["remaining"] == 0
    assert service.check_watches(db, FP, now=NOW)["watches"] == 0


def test_bad_update_keeps_the_old_watch_and_strangers_cannot_touch_it(db):
    w = service.watch_intent(db, FP, {"title": ["perception"]}, now=NOW)
    with pytest.raises(OpenHireError) as e:
        service.manage_watch(db, FP, "update", watch_id=w["watch_id"], filters={"email": "a@b.c"})
    assert e.value.code == "ERR_PII_NOT_ACCEPTED"
    assert service.manage_watch(db, FP, "list")["count"] == 1
    with pytest.raises(OpenHireError) as e:
        service.manage_watch(db, "#someone-else-k2p7", "delete", watch_id=w["watch_id"])
    assert e.value.code == "ERR_WATCH_NOT_FOUND"
    with pytest.raises(OpenHireError):
        service.manage_watch(db, FP, "rename")


def test_search_total_out(db):
    total: dict = {}
    rows = service.search_jobs(db, title=["perception"], limit=10, now=NOW, total_out=total)
    assert len(rows) == 10 and total["matched"] == 15


def test_mcp_envelope(db, monkeypatch):
    from contextlib import contextmanager
    from openhire import mcp_server as ms

    @contextmanager
    def scope():
        yield db
    monkeypatch.setattr(ms, "session_scope", scope)
    monkeypatch.setattr(ms, "_await_index", lambda timeout=180.0: None)
    monkeypatch.setattr(ms, "_preparing", lambda: None)
    monkeypatch.setattr(service, "_now", lambda now=None: now or NOW)
    page1 = ms.search_jobs(title=["perception"], limit=10, envelope=True)
    assert page1["matched"] == 15 and page1["returned"] == 10 and page1["has_more"] and page1["next_offset"] == 10
    assert page1["headline"]["zh"].startswith("共 15 条，本页 10 条")
    page2 = ms.search_jobs(title=["perception"], limit=10, offset=10, envelope=True)
    assert page2["returned"] == 5 and page2["has_more"] is False and page2["next_offset"] is None
    assert isinstance(ms.search_jobs(title=["perception"], limit=10), list)   # default shape unchanged
