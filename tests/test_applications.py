"""check_applications (0.8.37, reports/112): an answer to "投了一堆简历都是已读不回，是真的在招人吗",
from the employer's own system, never from the employer's inbox."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Application, Base, Company, Job
from openhire.errors import OpenHireError

NOW = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)
FP = "#apps-k2p7x8q1z9"


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="waymo", name="Waymo", ats_vendor="greenhouse", ats_tenant="waymo"))
        for jid, verified_days, delisted in (("waymo:open", 0, None), ("waymo:closed", 0, NOW - dt.timedelta(days=2)),
                                             ("waymo:stale", 40, None)):
            s.add(Job(id=jid, company_id="waymo", title=jid, description_raw="", source="ats_public_api",
                      first_seen_at=NOW - dt.timedelta(days=60), verified_at=NOW - dt.timedelta(days=verified_days),
                      posted_at=NOW - dt.timedelta(days=50), delisted_at=delisted, skills=[], location="SF",
                      content_hash=jid, ghost_score=0.0, remote_policy="onsite",
                      apply_channel="https://boards.greenhouse.io/waymo/jobs/1"))
        s.flush()
        yield s


def test_follows_tracked_postings_and_says_which_to_stop_waiting_on(session):
    out = service.check_applications(session, FP, add_job_ids=["waymo:open", "waymo:closed", "waymo:stale", "nope:1"], now=NOW)
    assert out["counts"] == {"open": 1, "closed": 1, "not_verified_recently": 1, "total": 3}
    assert [r["status"] for r in out["applications"]] == ["closed", "not_verified_recently", "open"]
    assert out["unknown_job_ids"] == ["nope:1"] and "不用再等" in out["summary"]["zh"]
    assert all(r["kind"] == "tracked" for r in out["applications"])
    # Adding again does not double; removing stops following.
    again = service.check_applications(session, FP, add_job_ids=["waymo:open"], now=NOW)
    assert again["added"] == [] and again["counts"]["total"] == 3
    gone = service.check_applications(session, FP, remove_job_ids=["waymo:stale"], now=NOW)
    assert gone["removed"] == ["waymo:stale"] and gone["counts"]["total"] == 2


def test_tracking_is_never_an_authorization(session):
    service.check_applications(session, FP, add_job_ids=["waymo:open"], now=NOW)
    rows = session.execute(select(Application)).scalars().all()
    assert len(rows) == 1 and rows[0].authorized is False and rows[0].delivered_via == service.TRACKED_VIA
    # An authorization of the same posting is still recorded as one, and listed once.
    receipt = service.apply(session, "waymo:open", FP, True)
    assert "already_authorized" not in receipt
    out = service.check_applications(session, FP, now=NOW)
    assert out["counts"]["total"] == 1


def test_authorized_applications_show_up_without_adding(session):
    service.apply(session, "waymo:closed", FP, True)
    out = service.check_applications(session, FP, now=NOW)
    assert out["applications"][0]["kind"] == "authorized" and out["applications"][0]["status"] == "closed"


def test_refuses_personal_data_as_fingerprint_or_id(session):
    with pytest.raises(OpenHireError):
        service.check_applications(session, "张三\n13800000000\n本科 5 年经验", now=NOW)


def test_empty_says_how_to_start(session):
    out = service.check_applications(session, FP, now=NOW)
    assert out["counts"]["total"] == 0 and "add_job_ids" in out["summary"]["en"]
