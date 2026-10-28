"""A posting is live only while the employer's own system returned it within 30 days
(the maintainer, 2026-10-28, reports/101). Four Greenhouse boards moved in September; the
crawl leaves rows alone when a board fails, so 416 rows confirmed one to two months
earlier sat in every search and every published figure. The window counts back from the
newest verification in the index, so an old copy of the index is not emptied by the clock."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job

NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone.utc)


def _job(jid, cid, verified_days_ago):
    v = NOW - dt.timedelta(days=verified_days_ago)
    return Job(id=f"{cid}:{jid}", company_id=cid, title="Perception Engineer", skills=["perception"],
               remote_policy="onsite", location="Shanghai", first_seen_at=v - dt.timedelta(days=5),
               posted_at=v - dt.timedelta(days=5), verified_at=v, source="ats_public_api",
               content_hash=f"h{cid}{jid}", ghost_score=0.0, apply_channel=f"https://jobs.lever.co/{cid}/{jid}")


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="fresh", name="Fresh Co", ats_vendor="lever", ats_tenant="fresh"))
        s.add(Company(id="moved", name="Moved Board Co", ats_vendor="greenhouse", ats_tenant="moved"))
        s.add(Company(id="mixed", name="Mixed Co", ats_vendor="lever", ats_tenant="mixed"))
        s.add(_job(1, "fresh", 0))       # verified in the newest crawl
        s.add(_job(2, "fresh", 29))      # inside the window
        s.add(_job(1, "moved", 31))      # board gone since September
        s.add(_job(2, "moved", 58))
        s.add(_job(1, "mixed", 2))
        s.add(_job(2, "mixed", 45))
        s.commit()
        yield s


def test_search_drops_rows_not_confirmed_for_30_days(db):
    ids = {r["job_id"] for r in service.search_jobs(db, limit=50, now=NOW)}
    assert ids == {"fresh:1", "fresh:2", "mixed:1"}


def test_window_counts_back_from_the_newest_verification_not_the_clock(db):
    """Read a month later with no refresh in between: nothing is emptied by the calendar."""
    later = NOW + dt.timedelta(days=60)
    ids = {r["job_id"] for r in service.search_jobs(db, limit=50, now=later)}
    assert ids == {"fresh:1", "fresh:2", "mixed:1"}


def test_company_info_counts_live_and_reports_the_unconfirmed(db):
    moved = service.get_company_info(db, "moved", now=NOW)
    assert moved["active_jobs"] == 0 and moved["unverified_over_30d"] == 2
    mixed = service.get_company_info(db, "mixed", now=NOW)
    assert mixed["active_jobs"] == 1 and mixed["unverified_over_30d"] == 1
    assert service.get_company_info(db, "fresh", now=NOW)["unverified_over_30d"] == 0


def test_live_employer_count_and_watches_follow_the_rule(db):
    assert service.live_employer_count(db) == 2
    w = service.watch_intent(db, "#window-k2p7x8q1", {"skills": ["perception"]}, now=NOW)
    assert w["matching_now"] == 3


def test_an_employer_with_only_unconfirmed_rows_says_so(db):
    out = service.diagnose_empty_search(db, company="moved")
    assert out["status"] == "not_verified_recently"
    assert "board" in out["hint"] and "says nothing about whether it is hiring" in out["hint"]
    assert "30" in out["headline"]["zh"]
    # an employer with fresh rows that simply do not match keeps the ordinary answer
    assert service.diagnose_empty_search(db, company="fresh", role_family="hr")["status"] == "no_match"


def test_empty_index_has_no_cutoff():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        assert service.verified_cutoff(s) is None
        assert service.search_jobs(s, now=NOW) == []
