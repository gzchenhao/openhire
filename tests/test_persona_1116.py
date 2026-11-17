"""Persona night 2026-11-16 (reports/147).

* Agility wrote "Applicants must have current authorization to work in the United States."
  and the row said the posting was silent on visas; the first answer passed that on (high).
* "Senior Staff Engineer, Test Director (R5446)" came back to a manager-only search as a
  director.
* "31 without location" was read as 31 in China; 25 were abroad.
* hiring_trend's window ran to the index's newest read while the employer was last read 19
  days earlier, and "0 new, 0 down" was read as a quiet company.
"""
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.pipeline.extract import requirements_from_text, seniority_from_title, visa_sponsorship_from_text

NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("text", [
    "Applicants must have current authorization to work in the United States.",
    "Candidates must currently be authorized to work in the US.",
    "You must already hold a valid work authorization to work in Canada.",
])
def test_requiring_current_work_authorization_means_no_sponsorship(text):
    label, quote = visa_sponsorship_from_text(text)
    assert label == "not_offered"
    assert "authori" in quote


@pytest.mark.parametrize("text", [
    "You must be authorized to work in the U.S. by your start date.",
    "Are you currently authorized to work in the United States?",
])
def test_plain_authorization_wording_is_not_read_as_a_refusal(text):
    assert visa_sponsorship_from_text(text) == (None, None)


def test_requirements_carry_the_refusal():
    req = requirements_from_text("Software Engineer", "Applicants must have current authorization to work in the United States.")
    assert req["visa_sponsorship"] == "not_offered"


@pytest.mark.parametrize("title,level", [
    ("Senior Staff Engineer, Test Director (R5446)", "staff"),
    ("Principal Engineer, Flight Test Director", "staff"),
    ("Staff Engineer / Tech Lead Manager", "manager"),
    ("Director of Engineering", "director"),
    ("Test Director", "director"),
])
def test_an_engineer_graded_staff_is_not_a_director(title, level):
    assert seniority_from_title(title) == level


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="inceptio", name="嬴彻", ats_vendor="moka", ats_tenant="x", last_crawled_at=NOW))
        s.add(Company(id="waymo", name="Waymo", ats_vendor="greenhouse", ats_tenant="waymo", last_crawled_at=NOW))
        old = NOW - dt.timedelta(days=19)
        s.add(Job(id="inceptio:a", company_id="inceptio", title="测试经理", description_raw="测试经理", skills=["x"],
                  remote_policy="onsite", location="上海", first_seen_at=old - dt.timedelta(days=40), verified_at=old,
                  posted_at=old - dt.timedelta(days=40), source="ats_public_api", content_hash="a", ghost_score=0.0,
                  apply_channel="https://app.mokahr.com/x/a"))
        s.add(Job(id="waymo:b", company_id="waymo", title="Test Manager", description_raw="Test Manager", skills=["x"],
                  remote_policy="onsite", location="Mountain View, CA", first_seen_at=NOW, verified_at=NOW,
                  posted_at=NOW - dt.timedelta(days=2), source="ats_public_api", content_hash="b", ghost_score=0.0,
                  apply_channel="https://boards.greenhouse.io/waymo/jobs/1"))
        s.commit()
        yield s


def test_hiring_trend_says_when_the_employer_was_last_read(db):
    t = service.hiring_trend(db, "inceptio")
    assert t["employer_last_read"] == (NOW - dt.timedelta(days=19)).date().isoformat()
    assert t["days_unread_in_window"] == 19
    assert "没读到" in t["in_words"]["zh"] and "unread" in t["in_words"]["en"]
    fresh = service.hiring_trend(db, "waymo")
    assert fresh["days_unread_in_window"] == 0 and "没读到" not in fresh["in_words"]["zh"]


def test_dropping_location_says_the_count_is_worldwide(db):
    relax = service._relax_counts(db, now=NOW, location="苏州", title=["Test Manager", "测试经理"])
    assert relax["location"]["scope"] == "worldwide"
    hint = service._relax_hint(relax)
    assert "全球范围" in hint and "worldwide" in hint and "list_portals" in hint
