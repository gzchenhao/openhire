"""Degree and experience thresholds read from the posting's own words, and the entry_level
filter built on them (reports/110: 应届生 were the largest group of complaints in the Zhihu
pain map, and every one had to open each JD to find "3 年以上")."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.pipeline.extract import requirements_from_text


@pytest.mark.parametrize("title, text, degree, years, track, entry", [
    ("感知算法工程师", "硕士及以上学历，博士优先；3年以上相关经验", "master", 3, "experienced", False),
    ("Robotics Engineer", "BS required, MS or PhD preferred. 5+ years of experience", "bachelor", 5, "experienced", False),
    ("Staff Engineer", "8-10 years of experience in perception; PhD a plus", None, 8, "experienced", False),
    ("Research Scientist", "PhD in robotics. A Master’s in ML is a plus.", "phd", None, "unknown", None),
    ("2027届校招-运动控制算法工程师", "本科及以上学历", "bachelor", None, "campus", True),
    ("Software Engineering Intern", "Pursuing a BS in CS", "bachelor", None, "intern", True),
    ("测试工程师", "本科及以上，经验不限", "bachelor", 0, "unknown", True),
    ("Product Designer", "", None, None, "unknown", None),
])
def test_requirements_from_text_table(title, text, degree, years, track, entry):
    r = requirements_from_text(title, text)
    assert (r["min_degree"], r["min_years"], r["hire_track"], r["entry_level"]) == (degree, years, track, entry)


def test_a_preferred_degree_is_not_a_requirement():
    assert requirements_from_text("x", "博士优先")["min_degree"] is None
    assert requirements_from_text("x", "Master's degree preferred")["min_degree"] is None


def test_is_entry_level_uses_title_level_too():
    assert service.is_entry_level("Junior Backend Engineer", "")
    assert not service.is_entry_level("Backend Engineer", "")              # says nothing: left out
    assert not service.is_entry_level("Backend Engineer", "5+ years of experience")
    assert not service.is_entry_level("Associate Technician", "2+ years of experience required")
    assert not service.is_entry_level("Manufacturing Engineering Manager", "接受应届生")


def test_a_team_description_is_not_an_invitation():
    boiler = "Our team consists of people from new graduates to domain experts."
    assert requirements_from_text("Robotics Software Engineer", boiler)["entry_level"] is None
    assert requirements_from_text("Robotics Software Engineer", "New grads welcome.")["entry_level"] is True


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s


def test_search_watch_and_rows_carry_requirements(session):
    now = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)
    session.add(Company(id="unitree", name="Unitree", ats_vendor="moka", ats_tenant="unitree"))
    for i, (title, jd) in enumerate([
        ("2027届校招-算法工程师", "硕士及以上学历"),
        ("算法工程师", "本科及以上，5年以上经验"),
        ("算法工程师", "负责运动控制"),
    ]):
        session.add(Job(id=f"unitree:{i}", company_id="unitree", title=title, description_raw=jd,
                        source="ats_public_api", first_seen_at=now, verified_at=now, posted_at=now,
                        skills=[], location="杭州", content_hash=f"h{i}", ghost_score=0.0,
                        remote_policy="onsite", apply_channel=f"https://app.mokahr.com/x/{i}"))
    session.flush()
    rows = service.search_jobs(session, now=now)
    by_id = {r["job_id"]: r["requirements"] for r in rows}
    assert by_id["unitree:0"]["hire_track"] == "campus" and by_id["unitree:0"]["min_degree"] == "master"
    assert by_id["unitree:1"]["min_years"] == 5 and by_id["unitree:1"]["entry_level"] is False
    assert by_id["unitree:2"]["entry_level"] is None
    assert [r["job_id"] for r in service.search_jobs(session, entry_level=True, now=now)] == ["unitree:0"]
    w = service.watch_intent(session, "#entry-k2p7x8q1", {"entry_level": True}, now=now)
    assert w["matching_now"] == 1
    out = service.diagnose_empty_search(session, entry_level=True, title=["nothing-like-this"])
    assert out["filters_applied"]["entry_level"] is True


def test_mcp_search_schema_has_entry_level():
    import asyncio
    from openhire.mcp_server import mcp
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert "entry_level" in tools["search_jobs"].inputSchema["properties"]


def test_sector_thermometer_counts_two_windows_by_posting_date(session):
    now = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)
    session.add(Company(id="waymo", name="Waymo", ats_vendor="greenhouse", ats_tenant="waymo"))
    for i, days in enumerate([1, 10, 29, 40, 75]):
        session.add(Job(id=f"waymo:{i}", company_id="waymo", title="Engineer", description_raw="",
                        source="ats_public_api", first_seen_at=now, verified_at=now,
                        posted_at=now - dt.timedelta(days=days), skills=[], location="X",
                        content_hash=f"t{i}", ghost_score=0.0, remote_policy="onsite",
                        apply_channel="https://boards.greenhouse.io/waymo/jobs/1"))
    session.flush()
    t = service.sector_thermometer(session)
    assert t["window_end"] == "2026-10-30"
    assert t["by_sector"]["autonomous_driving"] == {"last_30d": 3, "prior_30d": 1, "change_pct": 200}
    assert t["by_sector"]["embodied_ai"]["change_pct"] is None


# --- visa sponsorship as the posting states it (reports/124) ------------------------------
from openhire.pipeline.extract import visa_sponsorship_from_text as visa


@pytest.mark.parametrize("text, expected", [
    ("You must be independently authorized to work in the U.S. We are unable to sponsor or take over "
     "sponsorship of an employment visa for this role, at this time.", "not_offered"),
    ("Please note that visa sponsorship is not available for this position.", "not_offered"),
    ("Must be eligible to work in the United States; no H1-B visa sponsorship available.", "not_offered"),
    ("Applicants must have work authorization that does not require sponsorship from the company now or in the future.", "not_offered"),
    ("Due to federal contract requirements, U.S. citizenship is required.", "not_offered"),
    ("We do sponsor and take over sponsorship of employment visas for this role.", "offered"),
    ("If applicable, Kodiak may provide visa sponsorship for eligible candidates.", "offered"),
    ("Relocation support with visa sponsorship", "offered"),
    ("本岗位可办理工作签证。", "offered"),
    ("本岗位不提供工作签证。", "not_offered"),
    ("Partner with executive sponsors to scope projects. Company-paid 401(k).", None),
    ("Comply with export laws without sponsorship for an export license.", None),
    ("Build perception models in C++.", None),
])
def test_visa_sponsorship_reads_only_the_postings_own_sentence(text, expected):
    found, quote = visa(text)
    assert found == expected
    assert (quote is None) == (expected is None)


def test_a_caveat_in_the_next_sentence_stays_with_the_quote():
    found, quote = visa("Visa sponsorship: We do sponsor visas! However, we aren't able to successfully "
                        "sponsor visas for every role and every candidate. Apply anyway.")
    assert found == "offered" and "for every role" in quote and "Apply anyway" not in quote


def test_check_before_apply_carries_the_visa_line(session):
    now = dt.datetime(2026, 10, 31, tzinfo=dt.timezone.utc)
    session.add(Company(id="aeva", name="Aeva", ats_vendor="greenhouse", ats_tenant="aeva"))
    filler = " Build lidar perception pipelines for autonomous vehicles in Python and C++." * 8
    for i, jd in enumerate([
        "Visa sponsorship is not available for this role." + filler,
        "We do sponsor visas for this role." + filler,
        filler,
        "负责点云感知算法研发，本科及以上学历，3年以上经验，熟悉C++与ROS。" * 6,
    ]):
        session.add(Job(id=f"aeva:{i}", company_id="aeva", title="Perception Engineer", description_raw=jd,
                        source="ats_public_api", first_seen_at=now, verified_at=now, posted_at=now,
                        skills=[], location="Mountain View, CA", content_hash=f"v{i}", ghost_score=0.0,
                        remote_policy="onsite", apply_channel=f"https://boards.greenhouse.io/aeva/jobs/{i}"))
    session.flush()
    rows = {r["job_id"]: r for r in service.search_jobs(session, now=now)}
    codes = {jid: {c["code"] for c in r["check_before_apply"]} for jid, r in rows.items()}
    assert "visa_sponsorship_not_offered" in codes["aeva:0"]
    assert "visa_sponsorship_offered" in codes["aeva:1"]
    assert "visa_sponsorship_not_stated" in codes["aeva:2"]
    assert not any(c.startswith("visa_") for c in codes["aeva:3"]), "a Chinese posting is not flagged"
    assert rows["aeva:0"]["requirements"]["visa_quote"].startswith("Visa sponsorship is not available")
