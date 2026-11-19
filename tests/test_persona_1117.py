"""Persona night 2026-11-17 (reports/152): no high findings; three medium ones fixed."""
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job, Watch
from openhire.pipeline.extract import requirements_from_text

NOW = dt.datetime(2026, 11, 17, 12, 0, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("text,want", [
    ("designed for an operator with 8–10+ years of experience", 8),
    ("8 to 10 years of experience", 8),
    ("8-10 years of experience", 8),
    ("5+ years of experience", 5),
])
def test_a_range_of_years_starts_at_its_lower_end(text, want):
    assert requirements_from_text("Advisor", text)["min_years"] == want


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="zoox", name="Zoox", ats_vendor="greenhouse", ats_tenant="zoox", last_crawled_at=NOW))
        for i in range(14):
            fam = None if i == 0 else "engineering"
            s.add(Job(id=f"zoox:{i}", company_id="zoox", title="Warehouse Associate" if i == 0 else f"Perception Engineer {i}",
                      description_raw="x", skills=["perception"], remote_policy="onsite", location="Foster City, CA",
                      first_seen_at=NOW - dt.timedelta(days=i + 1), verified_at=NOW, posted_at=NOW - dt.timedelta(days=i + 1),
                      source="ats_public_api", content_hash=f"h{i}", ghost_score=0.0, role_family=fam,
                      apply_channel=f"https://boards.greenhouse.io/zoox/jobs/{i}"))
        s.commit()
        yield s


def test_an_unclassified_row_in_a_family_search_says_so(db):
    rows = service.search_jobs(db, role_family="engineering", limit=20, now=NOW)
    unclassified = [r for r in rows if not r.get("role_family")]
    assert unclassified and all("role_family_note" in r for r in unclassified)
    assert all("role_family_note" not in r for r in rows if r.get("role_family"))
    assert all("role_family_note" not in r for r in service.search_jobs(db, limit=20, now=NOW))


def test_a_baseline_names_every_posting_it_did_not_list(db):
    service.watch_intent(db, "#abcdef-abcdef-abcdef-abcdef", {"skills": ["perception"]})
    out = service.check_watches(db, "#abcdef-abcdef-abcdef-abcdef", now=NOW)
    w = out["results"][0]
    listed = {r["job_id"] for r in w["baseline_postings"]}
    rest = set(w["baseline_not_listed_job_ids"])
    assert len(listed) == service.WATCH_PAGE and not listed & rest
    assert len(listed | rest) == w["total_matching"] == 14


@pytest.mark.parametrize("text,want", [
    ("BS, MS, or PhD in Computer Science, Robotics or related field", "bachelor"),
    ("B.S., M.S. or Ph.D. in EE", "bachelor"),
    ("BS/MS/PhD in Robotics", "bachelor"),
    ("MS or PhD in CS required", "master"),
    ("PhD in Robotics", "phd"),
    ("Proficient in MS Office and Excel", None),
])
def test_a_list_of_degrees_reads_as_its_lowest(text, want):
    # persona night 2026-11-18 (high): "BS, MS, or PhD" was read as a PhD requirement
    assert requirements_from_text("Engineer", text)["min_degree"] == want
