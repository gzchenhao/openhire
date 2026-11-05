"""Persona night 2026-11-04 (reports/139): one high and the mediums that were ours to fix.

High: "测试策略岗" was a manager with no reason given, and the assistant invented one. Each row
now says what its level rests on (seniority_basis, seniority_quote). Mediums: a marketing title
filed as HR; a 经理 title of unknown level passed an IC filter unflagged; the watch sentence on
unknown levels contradicted a row it counted; the fingerprint was read as the watch id; compact
rows still carried every empty field; a reader fix to remote_policy never reached unchanged
rows; a cached board read said "read live just now"; a 北森 campus link silently read the
social channel.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.ats.base import JobRecord
from openhire.db.models import Base, Company, Job
from openhire.pipeline.extract import is_hr_title, seniority_basis

NOW = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)


def _job(jid, title, desc="", days=10):
    posted = NOW - dt.timedelta(days=days)
    return Job(id=f"acme:{jid}", company_id="acme", title=title, description_raw=desc or title, skills=["x"],
               remote_policy="onsite", location="上海", first_seen_at=posted, verified_at=NOW, posted_at=posted,
               source="ats_public_api", content_hash=f"h{jid}", ghost_score=0.0,
               apply_channel=f"https://job-boards.greenhouse.io/acme/jobs/{jid}")


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme", last_crawled_at=NOW))
        s.add(_job("lead", "测试策略岗", "3、负责测试团队管理、工作统筹、技能培训与人才建设。"))
        s.add(_job("sr", "Senior Perception Engineer"))
        s.add(_job("mgr", "招聘经理", "负责社招与校招。"))
        s.commit()
        yield s


def _rows(db):
    return {r["job_id"]: r for r in service.search_jobs(db, limit=20, now=NOW)}


def test_every_row_says_what_its_level_rests_on(db):
    r = _rows(db)
    assert r["acme:lead"]["seniority"] == "manager" and r["acme:lead"]["seniority_basis"] == "description"
    assert "负责测试团队管理" in r["acme:lead"]["seniority_quote"]
    assert r["acme:sr"]["seniority_basis"] == "title" and "seniority_quote" not in r["acme:sr"]
    assert r["acme:mgr"]["seniority_basis"] == "none"
    assert seniority_basis("Engineer", "") == {"level": "unknown", "basis": "none", "quote": None}


def test_a_manager_title_of_unknown_level_is_flagged(db):
    codes = [c["code"] for c in _rows(db)["acme:mgr"]["check_before_apply"]]
    assert "manager_title_unclear" in codes
    assert "manager_title_unclear" not in [c["code"] for c in _rows(db)["acme:sr"]["check_before_apply"]]


def test_marketing_title_is_not_hr():
    assert is_hr_title("Senior Marketing Manager, Recruiting Events") is False
    assert is_hr_title("Technical Recruiter") is True


def test_watch_sentence_and_fingerprint_notice(db):
    w = service.watch_intent(db, "#n1104-k2p7x8q1", {"seniority": ["management"]}, now=NOW)
    assert w["matching_now"] == 1
    assert "职级判为 unknown" in w["what_happens_next"]["zh"] and "标题没写级别时" in w["what_happens_next"]["zh"]
    assert "not the watch_id" in w["fingerprint_notice"]


def test_compact_rows_leave_out_empty_fields(db):
    service.watch_intent(db, "#c1104-k2p7x8q1", {"title": ["perception"]}, now=NOW)
    row = service.check_watches(db, "#c1104-k2p7x8q1", now=NOW)["results"][0]["baseline_postings"][0]
    assert "salary_min" not in row and "matched_skills" not in row
    for k in ("verified_at", "source", "ghost_score", "response_sla_days", "apply_channel"):
        assert k in row
    assert len(json.dumps(row, ensure_ascii=False)) < 1200


def test_an_ats_workplace_fix_reaches_unchanged_rows(db):
    from openhire.pipeline.ingest import _update_job
    from openhire.pipeline.extract import HeuristicExtractor
    from openhire.pipeline.hashing import content_hash
    job = db.get(Job, "acme:sr")
    job.content_hash = content_hash(job.title, job.description_raw)
    rec = JobRecord(ats_job_id="sr", title=job.title, description_raw=job.description_raw, location="Remote-Friendly",
                    remote_hint="remote", apply_channel=job.apply_channel)
    stats = type("S", (), {"jobs_unchanged": 0, "jobs_updated": 0, "extractions": 0})()
    _update_job(job, rec, job.content_hash, HeuristicExtractor(), stats, NOW)
    assert stats.jobs_unchanged == 1 and job.remote_policy == "remote"


def test_cached_board_read_and_beisen_campus_note(db):
    from openhire.ats.base import FetchResult
    rec = JobRecord(ats_job_id="1", title="算法工程师", description_raw="x", location="北京",
                    apply_channel="https://galaxea.zhiye.com/social/detail?jobAdId=1", posted_at=NOW - dt.timedelta(days=3))
    service._BOARD_CACHE.clear()
    fetch = lambda v, t: FetchResult(ok=True, status=200, records=[rec])  # noqa: E731
    first = service.read_board(db, url="https://galaxea.zhiye.com/campus/jobs", now=NOW, fetch=fetch)
    assert "channel_note" in first and "校招" in first["channel_note"]["zh"]
    again = service.read_board(db, url="https://galaxea.zhiye.com/social/jobs", now=NOW + dt.timedelta(minutes=2), fetch=fetch)
    assert again["from_cache"] is True and "channel_note" not in again
    assert "取自" in again["postings"][0]["dates_in_words"]["zh"]
    assert "read live at" in again["postings"][0]["dates_in_words"]["en"]
