"""Persona nights 2026-11-07 and 11-09 (reports/143).

* title=["招聘", "Recruiter"] returned HRBP rows first and title_exclude=["HRBP"] threw out
  every 招聘 title: one synonym group joined recruiting and business-partner words.
* title_exclude=["BP"] left "销售HRBP" in: exclusion was word-anchored.
* A model-invented fingerprint ("#q7m2-x9kd-4tpw-r8vn") turned up in three unrelated runs; the
  third found the second's watch and was told it was "most likely your own".
"""
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job

NOW = dt.datetime(2026, 11, 9, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    when = NOW - dt.timedelta(days=3)
    with Session(engine, future=True) as s:
        s.add(Company(id="pudu", name="普渡科技", ats_vendor="lever", ats_tenant="pudu", last_crawled_at=NOW))
        for jid, title in [("a", "销售HRBP（深圳）"), ("b", "招聘经理"), ("c", "招聘专员"),
                           ("d", "Senior Technical Recruiter"), ("e", "HR Business Partner"),
                           ("f", "薪酬福利经理")]:
            s.add(Job(id=f"pudu:{jid}", company_id="pudu", title=title, description_raw=title, skills=["x"],
                      remote_policy="onsite", location="深圳", first_seen_at=when, verified_at=NOW,
                      posted_at=when, source="ats_public_api", content_hash=f"h{jid}", ghost_score=0.0,
                      apply_channel=f"https://jobs.lever.co/pudu/{jid}"))
        s.commit()
        yield s


def ids(db, **kw):
    return {r["job_id"].split(":")[1] for r in service.search_jobs(db, now=NOW, limit=20, **kw)}


def test_recruiting_words_reach_recruiting_titles_only(db):
    assert ids(db, title=["招聘专员", "招聘经理", "Recruiter", "Sourcer", "Talent Acquisition"]) == {"b", "c", "d"}
    assert ids(db, title=["hr"]) == {"a", "b", "c", "d", "e"}, "the broad word still reaches all HR titles"


def test_title_exclude_is_literal(db):
    assert ids(db, title=["hr"], title_exclude=["BP"]) == {"b", "c", "d", "e"}
    assert ids(db, title=["hr"], title_exclude=["HRBP", "business partner"]) == {"b", "c", "d"}


def test_the_spellings_used_are_narrow():
    assert "hrbp" not in service.expand_title_term("招聘")
    assert "recruit" in service.expand_title_term("招聘")


def test_fingerprint_new_is_minted_by_the_server_and_collisions_are_not_called_yours(db):
    a = service.watch_intent(db, "new", {"title": ["招聘"]}, now=NOW)
    b = service.watch_intent(db, "new", {"title": ["招聘"]}, now=NOW)
    assert a["fingerprint_minted"] is True and a["fingerprint"].startswith("#")
    assert a["fingerprint"] != b["fingerprint"] and len(a["fingerprint"]) >= 20
    service.watch_intent(db, "#q7m2-x9kd-4tpw-r8vn", {"title": ["招聘"]}, now=NOW)
    again = service.watch_intent(db, "#q7m2-x9kd-4tpw-r8vn", {"title": ["hr"]}, now=NOW)
    assert again["existing_watches"] == 1
    assert "most likely" not in again["fingerprint_notice"]
    assert '"new"' in again["fingerprint_notice"]


def test_years_under_a_preferred_heading_are_not_a_minimum():
    from openhire.pipeline.extract import requirements_from_text
    jd = ("About the role\nYou will design policy.\nYou may be a good fit if you have:\n"
          "Excellent written communication\nStrong collaboration skills\n"
          "Preferred qualifications\n5+ years of experience in policy development, trust and safety\n"
          "Logistics\nMinimum education: Bachelor's degree or equivalent\n")
    r = requirements_from_text("Policy Design Manager, Integrity and Authenticity", jd)
    assert r["min_years"] is None and r["hire_track"] == "unknown"
    # A required section after the preferred one still counts.
    r2 = requirements_from_text("x", "Preferred qualifications\nPhD\nRequirements\n3+ years of experience in robotics\n")
    assert r2["min_years"] == 3 and r2["min_degree"] is None
    r3 = requirements_from_text("x", "加分项：\n博士学历\n任职要求：\n3年以上相关工作经验\n")
    assert r3["min_years"] == 3 and r3["min_degree"] is None


def test_robot_force_control_is_not_an_hr_title():
    assert service.title_matches("机器人力控算法工程师", ["hr"]) is False
    assert service.title_matches("人力资源经理", ["hr"]) is True
    assert service.title_matches("机器人事业部人力资源BP", ["人力"]) is True


def test_top_level_baseline_count_is_the_sum_of_the_watches(db):
    service.watch_intent(db, "#sum-k2p7-x8q1-z9", {"title": ["hr"]}, now=NOW)
    service.watch_intent(db, "#sum-k2p7-x8q1-z9", {"title": ["招聘"]}, now=NOW)
    out = service.check_watches(db, "#sum-k2p7-x8q1-z9", now=NOW)
    assert out["baseline_count"] == sum(r["baseline_count"] for r in out["results"]) == 5 + 3
