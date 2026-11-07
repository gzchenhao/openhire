"""Persona night 2026-11-06 (reports/142)."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.pipeline.extract import seniority_from_title

NOW = dt.datetime(2026, 11, 6, 12, 0, tzinfo=dt.timezone.utc)


def _job(jid, title, *, rf=None, remote="onsite", location="上海", desc=None):
    when = NOW - dt.timedelta(days=5)
    return Job(id=f"acme:{jid}", company_id="acme", title=title, description_raw=desc or title, skills=["x"],
               remote_policy=remote, location=location, first_seen_at=when, verified_at=NOW, posted_at=when,
               role_family=rf, source="ats_public_api", content_hash=f"h{jid}", ghost_score=0.0,
               apply_channel=f"https://jobs.lever.co/acme/{jid}")


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme", ats_vendor="lever", ats_tenant="acme", last_crawled_at=NOW))
        s.add(_job("pm", "项目经理（人形算法方向）"))
        s.add(_job("mk", "Senior Marketing Manager, Recruiting Events", rf="hr"))
        s.add(_job("rec", "Technical Recruiter", rf="hr"))
        s.add(_job("us", "Remote Engineer", remote="remote", location="Remote - US",
                   desc="Remote. Candidates must be located in the United States."))
        s.add(_job("ww", "Remote Engineer Anywhere", remote="remote", location="Remote - Worldwide",
                   desc="Fully remote, work from anywhere in the world."))
        s.commit()
        yield s


def _rows(db, **kw):
    return {r["job_id"]: r for r in service.search_jobs(db, now=NOW, limit=20, **kw)}


def test_chinese_function_manager_is_not_flagged(db):
    assert "manager_title_unclear" not in [c["code"] for c in _rows(db)["acme:pm"]["check_before_apply"]]


def test_incident_manager_is_an_individual_contributor():
    assert seniority_from_title("Incident Manager, Safeguards") == "unknown"


def test_marketing_title_stored_as_hr_reads_as_marketing(db):
    hr = _rows(db, role_family="hr")
    assert "acme:rec" in hr and "acme:mk" not in hr
    assert _rows(db)["acme:mk"]["role_family"] == "marketing"


def test_watch_takes_remote_scope(db):
    w = service.watch_intent(db, "#rs-k2p7x8q1", {"title": ["remote"], "remote_scope": "worldwide"}, now=NOW)
    pulled = service.check_watches(db, "#rs-k2p7x8q1", now=NOW)["results"][0]["baseline_postings"]
    assert w["matching_now"] == len(pulled) and all(p["remote_scope"] == "worldwide" for p in pulled)
    assert "acme:us" not in {p["job_id"] for p in pulled}


def test_rdap_note_matches_the_suffix(monkeypatch):
    from openhire.verify import checks

    class R:
        status_code = 404
    monkeypatch.setattr(checks, "_get", lambda url, **kw: R())
    com = checks.domain_age("xinghai-future.com")["note"]
    cn = checks.domain_age("example.cn")["note"]
    assert ".cn 域名常见" not in com and "lookup.icann.org" in com and ".cn 域名常见" in cn
