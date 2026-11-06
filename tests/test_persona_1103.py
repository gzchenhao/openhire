"""Persona night 2026-11-03 (reports/138): what ten simulated job seekers caught, pinned.

Two highs: an employer's published pay range dropped as implausible was then reported as "no
salary stated"; "Policy Design Manager" was a people manager on the word alone. Mediums:
a title naming no level hid a management role whose text says 负责测试团队管理; a 3-year role
passed a new graduate's filter; the first check_watches pull came back as 26 "new_matches"
at 68,000 characters; filters_applied lost remote_scope; the no_match hint named a filter
nobody sent; updated_at was read as an edit; 校招 under /social/; days_open off by one
between read_board and the index; a -04:00 offset stored as UTC; "Remote-Friendly" rows
marked onsite; no way to exclude a title word.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire import service
from openhire.ats.base import JobRecord, _iso_to_dt
from openhire.ats.greenhouse import GreenhouseClient
from openhire.db.models import Base, Company, Job, Watch
from openhire.pipeline.extract import seniority_for, seniority_from_title

NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)
UTC = dt.timezone.utc


def _job(jid, cid, title, desc="", *, days=10, salary=None, period="annual", apply=None, updated_days=None,
         location="上海", first_seen=None):
    posted = NOW - dt.timedelta(days=days)
    smin, smax, cur = salary or (None, None, None)
    return Job(id=f"{cid}:{jid}", company_id=cid, title=title, description_raw=desc or title, skills=["perception"],
               remote_policy="onsite", location=location, first_seen_at=first_seen or posted, verified_at=NOW,
               posted_at=posted, updated_at=(NOW - dt.timedelta(days=updated_days)) if updated_days is not None else None,
               salary_min=smin, salary_max=smax, salary_currency=cur, salary_period=period,
               source="ats_public_api", content_hash=f"h{jid}", ghost_score=0.0,
               apply_channel=apply or f"https://job-boards.greenhouse.io/{cid}/jobs/{jid}")


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme", last_crawled_at=NOW))
        s.add(_job("intern", "acme", "Developer Productivity Intern", salary=(22, 27, "USD")))
        s.add(_job("policy", "acme", "Policy Design Manager, Integrity and Authenticity",
                   "You will be responsible for developing, refining, and maintaining policies. "
                   "You will serve as the policy owner for integrity and authenticity."))
        s.add(_job("testlead", "acme", "测试策略岗",
                   "1、制定整车测试策略；2、搭建测试体系；3、负责测试团队管理、工作统筹、技能培训与人才建设。"))
        s.add(_job("assist", "acme", "测试工程师", "协助团队管理相关事务，执行测试用例。3年以上测试经验。"))
        s.add(_job("fresh", "acme", "算法工程师", "负责感知算法开发与优化。"))
        s.add(_job("retail", "acme", "产品专家-上海-静安大融城店", "门店销售与顾客服务。"))
        s.add(_job("campus", "acme", "全栈工程师（校招）", "面向2027届毕业生。",
                   apply="https://acme.zhiye.com/social/detail?jobAdId=1"))
        s.add(_job("touched", "acme", "Perception Engineer", "Perception for robots.", updated_days=2))
        s.commit()
        yield s


def _rows(db, **kw):
    return {r["job_id"]: r for r in service.search_jobs(db, limit=50, now=NOW, **kw)}


# --- high 1: a published range we would not show as pay is "unclear", not "not stated" ------
def test_salary_published_but_implausible_is_unclear_not_unstated(db):
    r = _rows(db)["acme:intern"]
    assert r["salary_min"] is None and r["salary_max"] is None
    assert r["salary_note"] == "ats_range_below_plausible_floor"
    assert r["salary_raw"] == {"min": 22, "max": 27, "currency": "USD", "period": "annual"}
    codes = [c["code"] for c in r["check_before_apply"]]
    assert "salary_unclear" in codes and "salary_not_stated" not in codes
    # A row with no figures at all still says so.
    assert "salary_not_stated" in [c["code"] for c in _rows(db)["acme:fresh"]["check_before_apply"]]


# --- high 2 and the management mediums: the level a posting has --------------------------------
def test_seniority_reads_the_text_when_the_title_names_no_level():
    ic_policy = "You will be responsible for developing and maintaining policies. You will serve as the policy owner."
    assert seniority_for("Policy Design Manager, Integrity and Authenticity", ic_policy) == "unknown"
    assert seniority_for("Public Policy Manager", ic_policy) == "unknown"
    assert seniority_for("测试策略岗", "3、负责测试团队管理、工作统筹、技能培训与人才建设") == "manager"
    assert seniority_for("Head of Nothing But Title", "") == "director"            # the title still wins
    assert seniority_for("Engineering Manager, Perception", "no team words here") == "manager"
    assert seniority_for("测试工程师", "协助团队管理相关事务") == "unknown"              # helping is not leading
    assert seniority_for("Software Engineer", "Prior experience leading a team is a plus.") == "unknown"
    assert seniority_for("Software Engineer", "You will manage a team of five engineers.") == "manager"
    assert seniority_for("Software Engineer", "This role has four direct reports.") == "manager"
    # 专家 is a grade outside retail and a shop-floor title inside it.
    assert seniority_from_title("产品专家-上海-静安大融城店") == "unknown"
    assert seniority_from_title("可靠性设计专家") == "senior"


def test_management_search_reaches_a_title_that_names_no_level(db):
    titles = {r["title"] for r in service.search_jobs(db, seniority=["management"], now=NOW)}
    assert "测试策略岗" in titles
    assert "Policy Design Manager, Integrity and Authenticity" not in titles
    assert _rows(db)["acme:testlead"]["seniority"] == "manager"
    assert _rows(db)["acme:policy"]["seniority"] == "unknown"


def test_junior_end_filter_drops_three_year_rows_whose_title_names_no_level(db):
    titles = {r["title"] for r in service.search_jobs(db, seniority=["intern", "junior", "unknown"], now=NOW)}
    assert "算法工程师" in titles and "Developer Productivity Intern" in titles
    assert "测试工程师" not in titles, "3年以上 is not the junior end, whatever the title says"
    # Asked for every level, the same row is there: the rule applies to junior-only requests.
    assert "测试工程师" in {r["title"] for r in service.search_jobs(db, seniority=["unknown", "senior"], now=NOW)}


# --- title_exclude: "not 专家" enforced by the tool, in searches and on every watch pull ---------
def test_title_exclude_in_search_and_watch(db):
    rows = service.search_jobs(db, title=["专家", "perception"], title_exclude=["专家"], now=NOW)
    assert [r["title"] for r in rows] == ["Perception Engineer"]
    w = service.watch_intent(db, "#excl-k2p7x8q1", {"title": ["专家", "perception"], "title_exclude": ["专家"]}, now=NOW)
    assert w["matching_now"] == 1
    stored = db.execute(select(Watch).where(Watch.watch_id == w["watch_id"])).scalar_one()
    assert stored.filters["title_exclude"] == ["专家"]
    pulled = service.check_watches(db, "#excl-k2p7x8q1", now=NOW)
    assert [m["title"] for m in pulled["results"][0]["baseline_postings"]] == ["Perception Engineer"]


# --- check_watches: the first pull is a baseline with compact rows ------------------------------
def test_first_pull_is_a_baseline_with_compact_rows(db):
    fp = "#base-k2p7x8q1"
    service.watch_intent(db, fp, {"title": ["perception"]}, now=NOW)
    first = service.check_watches(db, fp, now=NOW)
    assert first["new_matches"] == 0 and first["baseline_count"] == 1
    r = first["results"][0]
    assert r["is_first_pull"] is True and r["new_matches"] == [] and r["baseline_count"] == 1
    row = r["baseline_postings"][0]
    assert row["job_id"] == "acme:touched"
    assert "dates_in_words" in row and "check_before_apply" in row and "apply_channel" in row
    for long_field in ("skills", "ghost_reason", "rank_score", "freshness", "role_group"):
        assert long_field not in row
    assert "baseline_postings" in first["summary"]["zh"] and "baseline_postings" in first["summary"]["en"]
    # An increment later is under new_matches, and nothing is a baseline any more.
    later = NOW + dt.timedelta(days=1)
    db.add(_job("newper", "acme", "Senior Perception Engineer", days=0, first_seen=later))
    db.commit()
    second = service.check_watches(db, fp, now=later + dt.timedelta(hours=1))
    assert second["new_matches"] == 1 and second["baseline_count"] == 0
    assert [m["job_id"] for m in second["results"][0]["new_matches"]] == ["acme:newper"]
    assert second["results"][0]["baseline_postings"] == []


# --- the empty answer: every filter echoed, and what each one alone hides ---------------------
def test_empty_result_echoes_every_filter_and_counts_what_each_hides(db):
    out = service.diagnose_empty_search(db, title=["perception"], seniority=["management"], now=NOW)
    assert out["status"] == "no_match"
    assert out["relax"]["seniority"] == {"matches_without_it": 1, "of_which_title_names_no_level": 1}
    assert out["relax"]["title"]["matches_without_it"] == 1          # 测试策略岗
    assert "unknown" in out["hint"] and "required_skills" not in out["hint"]
    echo = service.diagnose_empty_search(db, remote_scope="worldwide", remote=True, min_salary=1,
                                         require_stated_salary=True, title_exclude=["x"], now=NOW)["filters_applied"]
    assert echo["remote_scope"] == "worldwide" and echo["remote"] is True and echo["min_salary"] == 1
    assert echo["require_stated_salary"] is True and echo["title_exclude"] == ["x"]


def test_region_word_in_location_is_named(db):
    out = service.diagnose_empty_search(db, title=["perception"], location="APAC", now=NOW)
    assert out["status"] == "unknown_location" and "region" in out["hint"] and "remote_scope" in out["hint"]


# --- the row's own words ------------------------------------------------------------------------
def test_updated_at_is_glossed_on_the_row(db):
    r = _rows(db)["acme:touched"]
    assert r["days_since_update"] == 2
    assert "保存不等于内容有改动" in r["dates_in_words"]["zh"]
    assert "saved does not mean edited" in r["dates_in_words"]["en"]
    # A row the vendor has not touched since publishing says nothing about it.
    assert "保存" not in _rows(db)["acme:fresh"]["dates_in_words"]["zh"]


def test_campus_title_under_social_channel_gets_a_check_item(db):
    r = _rows(db)["acme:campus"]
    assert r["requirements"]["hire_track"] == "campus"
    assert "campus_posting_in_social_channel" in [c["code"] for c in r["check_before_apply"]]


def test_watch_says_what_it_cannot_see(db):
    w = service.watch_intent(db, "#blind-k2p7x8q1", {"title": ["perception"], "seniority": ["management"], "location": "上海"}, now=NOW)
    zh, en = w["what_happens_next"]["zh"], w["what_happens_next"]["en"]
    assert w["matching_now"] == 0 and "现在没有匹配的岗位" in zh and "Nothing matches right now" in en
    assert "unknown" in zh and "unknown" in en and "没写城市" in zh and "no location text" in en


# --- the adapters: same days, same instant, remote wins ---------------------------------------
def test_board_posting_days_open_are_calendar_days():
    rec = JobRecord(ats_job_id="1", title="Policy Analyst", description_raw="x", location="Remote",
                    apply_channel="https://job-boards.greenhouse.io/anthropic/jobs/1",
                    posted_at=dt.datetime(2026, 10, 13, 10, 0, tzinfo=UTC))
    assert service._board_posting(rec, NOW)["days_open"] == 21


def test_greenhouse_location_remote_beats_onsite_metadata():
    j = {"metadata": [{"name": "Location Type", "value": "On-site"}]}
    assert GreenhouseClient._remote_hint(j, "Remote-Friendly (Travel Required) | San Francisco, CA") == "remote"
    assert GreenhouseClient._remote_hint(j, "San Francisco, CA") == "onsite"


def test_iso_offsets_are_stored_as_utc():
    assert _iso_to_dt("2026-10-19T13:43:14-04:00") == dt.datetime(2026, 10, 19, 17, 43, 14, tzinfo=UTC)
    assert _iso_to_dt("2026-10-19T13:43:14Z") == dt.datetime(2026, 10, 19, 13, 43, 14, tzinfo=UTC)
    assert _iso_to_dt("2026-10-19T13:43:14") == dt.datetime(2026, 10, 19, 13, 43, 14)
