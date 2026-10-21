"""The "hr" role family (0.8.17): recruiting and people roles get a family of their own.

The maintainer asked for it on 2026-10-21 so recruiters notice OpenHire: until then their
own next job was filed under ops, next to finance and supply chain. These tests pin the
title rule (measured on the 2026-10-19 snapshot before it shipped), the free
reclassification the weekly refresh runs, the filter and its aliases, and the paid
passes skipping delisted postings.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire import service
from openhire.db import Job, init_db, session_scope
from openhire.db.models import Base, Company
from openhire.errors import OpenHireError
from openhire.pipeline import rebuild
from openhire.pipeline.extract import (
    _DEEPSEEK_ROLE_FAMILY_SYSTEM,
    ROLE_FAMILIES,
    classify_role_family_heuristic,
    is_hr_title,
)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 21, tzinfo=UTC)

# Real titles from the 2026-10-19 snapshot.
HR_TITLES = [
    "Sr. HR Business Partner", "Recruiter, AI Research", "Senior Talent Acquisition Partner, GTM",
    "Senior Technical Sourcer, Applications Engineering", "People Partner - Engineering",
    "Director of Recruiting, Engineering & IT, Bangalore India", "Sales Recruiter", "HRIS Manager",
    "Compensation & Total Rewards", "Senior Employee Relations Partner",
    "招聘经理(J11800)", "HRBP（研发）", "人事专员", "人力资源BP", "校园招聘专家", "海外招聘",
    "招聘（芯片方向）", "人力招聘-杭州", "HR实习生（招聘方向）", "组织与人才发展主管/经理",
    "雇主品牌内容运营", "高级招聘专员（机器人事业部）", "人事行政岗 （HR& Admin Operations）",
]
NOT_HR_TITLES = [
    # 人事 inside 机器人事业部 ("robotics business unit")
    "机器人算法工程师（机器人事业部）", "高级项目经理（机器人事业部）", "采购总监（机器人事业部）",
    # 招聘 as a programme label in front of another job
    "2027届校园招聘-感知算法工程师", "【社会招聘】嵌入式软件工程师", "间接采购高级专员（人力与行政方向）",
    # hr inside other words
    "Senior Electrical Engineer - HRI (Visuals)", "Contract Student Worker - Data Analyst (20 hrs/wk)",
    "Chrome Extension Engineer", "Perception Engineer", "感知算法工程师",
]


@pytest.mark.parametrize("title", HR_TITLES)
def test_hr_titles_are_hr(title):
    assert is_hr_title(title), title
    assert classify_role_family_heuristic(title) == "hr"


@pytest.mark.parametrize("title", NOT_HR_TITLES)
def test_lookalikes_are_not_hr(title):
    assert not is_hr_title(title), title
    assert classify_role_family_heuristic(title) != "hr"


def test_the_taxonomy_and_the_paid_prompt_both_know_hr():
    assert "hr" in ROLE_FAMILIES
    assert "hr" in _DEEPSEEK_ROLE_FAMILY_SYSTEM and "'Technical Recruiter' is 'hr'" in _DEEPSEEK_ROLE_FAMILY_SYSTEM
    # a recruiter for sales roles is a recruiter, not a sales job
    assert classify_role_family_heuristic("Recruiter, Enterprise Sales") == "hr"
    assert classify_role_family_heuristic("Account Executive") == "sales"
    assert classify_role_family_heuristic("Finance Manager") == "ops"


# --- the filter --------------------------------------------------------------------------
def _job(jid, title, role_family, *, delisted=False):
    return Job(id=f"acme:{jid}", company_id="acme", title=title, description_raw=title, skills=[],
               remote_policy="onsite", location="香港", posted_at=NOW - dt.timedelta(days=5),
               first_seen_at=NOW - dt.timedelta(days=5), verified_at=NOW, source="ats_public_api",
               apply_channel=f"https://boards.greenhouse.io/acme/jobs/{jid}", content_hash=f"h{jid}",
               ghost_score=0.0, role_family=role_family,
               delisted_at=(NOW - dt.timedelta(days=1)) if delisted else None,
               extraction_source="heuristic")


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme Robotics", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", verified=False, last_crawled_at=NOW))
        s.add(_job("rec", "Technical Recruiter", "hr"))
        s.add(_job("hrbp", "HRBP（研发）", "hr"))
        s.add(_job("eng", "机器人算法工程师（机器人事业部）", "engineering"))
        s.add(_job("fin", "Finance Manager", "ops"))
        s.commit()
        yield s


def test_role_family_hr_filters_and_its_aliases_resolve(session):
    def ids(rf):
        return {r["job_id"] for r in service.search_jobs(session, role_family=rf, now=NOW)}

    assert ids("hr") == {"acme:rec", "acme:hrbp"}
    for alias in ("recruiting", "Recruiting", "people", "招聘", "人力资源", "human resources"):
        assert ids(alias) == {"acme:rec", "acme:hrbp"}, alias
    assert ids("ops") == {"acme:fin"}


def test_unclassified_rows_join_an_hr_search_only_by_their_title(session):
    """43% of live rows had no family yet on 2026-10-19; "never hide an unread row" would
    have filled an hr search with them. The title rule decides instead."""
    session.add(_job("new-eng", "Perception Engineer", None))
    session.add(_job("new-rec", "招聘经理", None))
    session.add(_job("new-unsure", "Member of Technical Staff", None))
    session.commit()

    def ids(rf):
        return {r["job_id"] for r in service.search_jobs(session, role_family=rf, now=NOW)}

    assert ids("hr") == {"acme:rec", "acme:hrbp", "acme:new-rec"}
    eng = ids("engineering")
    assert {"acme:eng", "acme:new-eng", "acme:new-unsure"} <= eng and "acme:new-rec" not in eng


def test_an_unknown_family_is_still_refused_and_names_hr(session):
    with pytest.raises(OpenHireError) as ei:
        service.search_jobs(session, role_family="astrology", now=NOW)
    assert ei.value.code == "ERR_UNKNOWN_ROLE_FAMILY"
    assert "hr" in ei.value.message and "title" in ei.value.message


def test_a_title_search_for_hr_skips_the_robotics_business_unit(session):
    rows = {r["job_id"] for r in service.search_jobs(session, title=["人事"], now=NOW)}
    assert "acme:eng" not in rows
    assert service.title_matches("人事专员", ["人事"]) is True
    assert service.title_matches("机器人算法工程师（机器人事业部）", ["hr"]) is False


def test_a_watch_takes_the_hr_family(session):
    w = service.watch_intent(session, "#hr-fam-k2p7-x8q1", {"role_family": "招聘"}, now=NOW)
    assert w["status"] == "active"


# --- the free reclassification the weekly refresh runs ------------------------------------
@pytest.fixture()
def index_rows():
    init_db()
    with session_scope() as s:
        for t in (Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=NOW))
        s.add(_job("1", "Senior Technical Recruiter", "ops"))
        s.add(_job("2", "Staff Technical Sourcer - Aircraft Engineering", "engineering"))
        s.add(_job("3", "招聘经理", None))
        s.add(_job("4", "机器人算法工程师（机器人事业部）", "engineering"))
        s.add(_job("5", "Finance Manager", "ops"))
        s.add(_job("6", "HR Business Partner", "hr"))
    yield
    with session_scope() as s:
        for row in s.execute(select(Job)).scalars():
            s.delete(row)


def test_reclassify_hr_moves_hr_titles_from_any_family_once(index_rows):
    moved = rebuild.reclassify_hr()
    assert moved == {"ops": 1, "engineering": 1, "null": 1}
    with session_scope() as s:
        fam = {j.id: j.role_family for j in s.execute(select(Job)).scalars()}
    assert fam["acme:1"] == fam["acme:2"] == fam["acme:3"] == fam["acme:6"] == "hr"
    assert fam["acme:4"] == "engineering" and fam["acme:5"] == "ops"
    assert rebuild.reclassify_hr() == {}, "idempotent: a second run moves nothing"


def test_reclassify_hr_cli_reports_what_moved(index_rows):
    from typer.testing import CliRunner

    from openhire.cli import app

    res = CliRunner().invoke(app, ["reclassify-hr"])
    assert res.exit_code == 0 and "3" in res.output and "hr" in res.output


# --- the paid passes skip delisted postings -----------------------------------------------
class _FakeClassifier:
    def classify_role_family_with_usage(self, rec):
        return "engineering", 100, 5


def test_paid_role_family_pass_skips_delisted_unless_asked(index_rows, monkeypatch):
    with session_scope() as s:
        s.add(_job("7", "Perception Engineer", None))
        s.add(_job("8", "Old Perception Engineer", None, delisted=True))
    monkeypatch.setattr(rebuild, "make_deepseek_extractor", lambda: _FakeClassifier())
    stats = rebuild.rebuild_role_family(batch_size=10, workers=1, ceiling_cny=999)
    with session_scope() as s:
        fam = {j.id: j.role_family for j in s.execute(select(Job)).scalars()}
    assert fam["acme:7"] == "engineering" and fam["acme:8"] is None
    assert stats.total_target == 2  # 招聘经理 (still NULL: reclassify_hr not run here) and #7
    stats = rebuild.rebuild_role_family(batch_size=10, workers=1, ceiling_cny=999, include_delisted=True)
    with session_scope() as s:
        assert s.get(Job, "acme:8").role_family == "engineering"
