"""seniority: the level a title names, as a field and a hard filter (0.8.30, reports/100).

A tester searching Zoox for "perception" got "Senior Manager, Perception Data" first and
asked for the assistant to know "engineer or manager, how many years" before searching.
The rules are measured against titles from the 2026-10-26 snapshot; the table below is
the contract. Ranking is untouched: this is a filter like role_family, never a score input.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError
from openhire.pipeline.extract import SENIORITY_LEVELS, expand_seniority, seniority_from_title

NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone.utc)

TABLE = [
    # internships, whatever else the title says; "International" is not an intern
    ("Software Engineer Intern (2027)", "intern"),
    ("Deployment Strategist, Internship - US Government", "intern"),
    ("法务工商管理实习生", "intern"),
    ("iOS Developer, International", "unknown"),
    # director and above
    ("Director, Perception", "director"),
    ("Head of Marketing - Symmetry", "director"),
    ("Regional VP, Sales (South East Asia)", "director"),
    ("Chief Compliance Officer, UK", "director"),
    ("零售门店总经理-安庆", "director"),
    ("教育BG-储备运营总监-全国", "director"),
    ("金融运营负责人", "director"),
    ("Lakebase Associate Director Specialist-MFG", "director"),
    ("Director and Managing Associate General Counsel", "director"),
    # top individual contributors, not executives
    ("具身智能首席科学家(J17819)", "staff"),
    ("首席互联架构师（Switch芯片与网络系统方向）(J10879)", "staff"),
    # people managers
    ("Senior Manager, Perception Data", "manager"),
    ("Engineering Manager, Perception", "manager"),
    ("Tech Lead Manager, Connectors", "manager"),
    ("Associate Manager, Internal Audit", "manager"),
    ("Manager, Technical Program Management - Artificial Intelligence", "manager"),
    ("量产技术经理", "manager"),
    # function managers lead a product or an account, not people
    ("Senior Product Manager", "senior"),
    ("Staff Product Manager", "staff"),
    ("Principal Partner Program Manager - Resellers", "staff"),
    ("Technical Program Manager, SOX Compliance", "unknown"),
    ("Product Manager", "unknown"),
    ("智能座舱软件产品经理（系统应用方向）- 北京", "unknown"),
    ("销售经理（轨道交通）", "unknown"),
    ("中级交付项目经理", "unknown"),
    # leads
    ("Offensive Security Lead", "lead"),
    ("Senior Lead of Physical Security", "lead"),
    ("IT Leader", "lead"),
    ("导航算法组长（slam方向）", "lead"),
    ("机器人机电控制团队负责人-驱动器方向", "lead"),
    ("财务主管", "lead"),
    ("感知融合算法工程师/主管", "unknown"),   # a grade option on an engineer posting
    ("行政专员/主管", "unknown"),
    ("高级泊车系统工程师/主管", "senior"),
    # staff and principal
    ("Staff Backend Engineer - Licensing & Revenue Platform", "staff"),
    ("Principal Engineer - Privacy", "staff"),
    ("Senior Staff Machine Learning Engineer", "staff"),
    ("Distinguished Architect, AI", "staff"),
    ("高级系统架构师", "staff"),
    ("Member of Technical Staff, Data Analysis and Evaluation", "unknown"),
    ("Senior Member of Technical Staff, Web Data", "senior"),
    # senior
    ("Senior Machine Learning Engineer - Perception 3D Segmentation", "senior"),
    ("Sr. Software Engineer", "senior"),
    ("可靠性设计专家", "senior"),
    ("Senior Customer Care Associate", "senior"),
    # junior and entry level
    ("Graduate Software Engineer", "junior"),
    ("海外销售助理", "junior"),
    ("（校招）决策规划算法工程师-枢纽", "junior"),
    ("Strategy & Planning Associate", "junior"),
    # no level named: never guessed
    ("Perception Deployment Engineer - Model Deployment & Optimization", "unknown"),
    ("Data Scientist - Perception Verification and Validation", "unknown"),
    ("Machine Learning Fellow - Human Frontier Collective", "unknown"),
    ("", "unknown"),
    (None, "unknown"),
]


@pytest.mark.parametrize("title,expected", TABLE, ids=[str(t)[:40] for t, _ in TABLE])
def test_seniority_from_title(title, expected):
    assert seniority_from_title(title) == expected


def test_every_value_is_a_known_level():
    for title, _ in TABLE:
        assert seniority_from_title(title) in SENIORITY_LEVELS


def test_aliases_expand_and_plain_levels_pass_through():
    assert expand_seniority(None) is None and expand_seniority([]) is None
    assert expand_seniority(["ic"]) == {"intern", "junior", "senior", "staff", "unknown"}
    assert expand_seniority(["management"]) == {"lead", "manager", "director"}
    assert expand_seniority(["Senior", "staff"]) == {"senior", "staff"}
    assert expand_seniority(["个人贡献者", "lead"]) == {"intern", "junior", "senior", "staff", "unknown", "lead"}


def test_unknown_values_are_refused_not_ignored():
    with pytest.raises(OpenHireError) as e:
        service.check_seniority(["senoir"])
    assert e.value.code == "ERR_UNKNOWN_SENIORITY"
    assert service.check_seniority("IC") == ["ic"]
    assert service.check_seniority(None) is None


def _job(jid, title, days=10):
    when = NOW - dt.timedelta(days=days)
    return Job(id=f"zoox:{jid}", company_id="zoox", title=title, description_raw=title, skills=["perception"],
               remote_policy="onsite", location="Foster City, CA", first_seen_at=when, verified_at=NOW,
               posted_at=when, source="ats_public_api", content_hash=f"h{jid}", ghost_score=0.0,
               apply_channel=f"https://jobs.lever.co/zoox/{jid}")


@pytest.fixture()
def zoox():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="zoox", name="Zoox", ats_vendor="lever", ats_tenant="zoox", last_crawled_at=NOW))
        s.add(_job(1, "Senior Manager, Perception Data", days=35))        # newest after the engineer
        s.add(_job(2, "Perception Deployment Engineer", days=28))
        s.add(_job(3, "Senior Machine Learning Engineer - Perception", days=103))
        s.add(_job(4, "Director, Perception", days=366))
        s.add(_job(5, "Perception Engineering Intern", days=5))
        s.commit()
        yield s


def test_ic_filter_keeps_the_manager_and_director_out(zoox):
    rows = service.search_jobs(zoox, title=["perception"], seniority=["ic"], now=NOW)
    titles = [r["title"] for r in rows]
    assert "Senior Manager, Perception Data" not in titles and "Director, Perception" not in titles
    assert titles[0] == "Perception Engineering Intern"           # newest, still ranked by freshness
    assert {r["seniority"] for r in rows} == {"intern", "unknown", "senior"}


def test_management_filter_and_single_levels(zoox):
    mgmt = service.search_jobs(zoox, title=["perception"], seniority=["management"], now=NOW)
    assert {r["seniority"] for r in mgmt} == {"manager", "director"}
    senior = service.search_jobs(zoox, title=["perception"], seniority=["senior", "unknown"], now=NOW)
    assert [r["title"] for r in senior] == ["Perception Deployment Engineer", "Senior Machine Learning Engineer - Perception"]
    assert service.search_jobs(zoox, seniority=["junior"], now=NOW) == []


def test_no_filter_means_every_level_and_the_field_is_on_every_row(zoox):
    rows = service.search_jobs(zoox, now=NOW)
    assert len(rows) == 5 and all(r["seniority"] in SENIORITY_LEVELS for r in rows)


def test_watch_accepts_seniority_and_applies_it_on_every_pull(zoox):
    w = service.watch_intent(zoox, "#seniority-k2p7x8q1", {"title": ["perception"], "seniority": ["ic"]}, now=NOW)
    assert w["matching_now"] == 3
    stored = zoox.get(service.Watch, w["watch_id"]).filters
    assert stored["seniority"] == ["ic"]
    pulled = service.check_watches(zoox, "#seniority-k2p7x8q1", now=NOW)
    titles = {m["title"] for r in pulled["results"] for m in r["new_matches"]}
    assert "Senior Manager, Perception Data" not in titles and len(titles) == 3
    with pytest.raises(OpenHireError) as e:
        service.watch_intent(zoox, "#seniority-k2p7x8q1", {"seniority": ["boss"]}, now=NOW)
    assert e.value.code == "ERR_UNKNOWN_SENIORITY"


def test_ranking_signature_untouched():
    """Red line 2: seniority is a filter, never an input to rank_score."""
    import inspect

    from openhire.pipeline.ranking import rank_score

    assert list(inspect.signature(rank_score).parameters) == ["match_quality", "freshness"]
