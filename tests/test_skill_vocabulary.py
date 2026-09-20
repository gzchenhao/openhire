"""One skill, several spellings — and a search that could not reach its own data.

The LLM extractor emits free-form tags and nothing normalised them, so the index holds
"autonomous driving" (54 rows), "autonomous-driving" (81) and "autonomous_driving" (1) as
three different skills. Measured 2026-09-20 over the live index: 1,263 groups differ ONLY
by hyphen / space / underscore, covering 2,805 tags and 13,116 row-occurrences. Searching
the commonest spelling of "autonomous driving" missed 40% of the rows that have it;
"data analysis" missed 58%.

A reviewer read that as "OpenHire has no autonomous-driving coverage at XPeng". The
coverage was there. The query could not reach it.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.pipeline.ranking import normalize_skill

NOW = dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("a,b", [
    ("autonomous-driving", "autonomous driving"),
    ("autonomous_driving", "autonomous driving"),
    ("computer-vision", "Computer Vision"),
    ("deep learning", "deep-learning"),
    ("  data_analysis ", "data analysis"),
])
def test_separator_spellings_fold_together(a, b):
    assert normalize_skill(a) == normalize_skill(b)


@pytest.mark.parametrize("a,b", [
    ("c++", "c"),          # stripping punctuation would merge three languages
    ("c#", "c"),
    ("react", "react native"),
    ("go", "golang"),      # a real synonym, but NOT a separator difference: out of scope
])
def test_it_folds_separators_and_nothing_else(a, b):
    assert normalize_skill(a) != normalize_skill(b)


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = Session(engine, future=True)
    s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme"))
    for i, tag in enumerate(["computer vision", "computer-vision", "computer_vision"]):
        s.add(Job(
            id=f"acme:{i}", company_id="acme", title=f"Perception Engineer {i}",
            description_raw="", skills=[tag, "python"], remote_policy="remote",
            salary_inferred=False, first_seen_at=NOW, verified_at=NOW,
            posted_at=NOW, source="ats_public_api", relist_count=0, ghost_score=0.0,
            content_hash=f"h{i}",
            apply_channel="https://boards.greenhouse.io/embed/job_app?for=acme&token=1",
        ))
    s.flush()
    yield s
    s.close()


@pytest.mark.parametrize("query", ["computer vision", "computer-vision", "Computer_Vision"])
def test_any_spelling_finds_every_row(session, query):
    rows = service.search_jobs(session, [query], None, None, 10, now=NOW)
    assert len(rows) == 3, f"{query!r} should reach all three spellings"
    for r in rows:
        assert r["match_quality"] == 1.0
        # Reported in the ROW's own spelling: that is what the posting actually says.
        assert r["matched_skills"], "a matched row must name the tag it matched on"


def test_a_spelling_difference_is_not_reported_as_an_unknown_tag(session):
    """diagnose_empty_search used to compare raw strings, so it would tell a caller that
    "computer-vision" exists nowhere in an index that is full of "computer vision"."""
    out = service.diagnose_empty_search(session, skills=["computer-vision", "cobol"])
    assert out["unknown_skills"] == ["cobol"]
