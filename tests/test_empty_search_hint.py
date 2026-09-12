"""An empty search must say WHY it is empty.

A bare `[]` is the same answer to two different questions: "is anyone hiring for this?"
and "did I spell the tag right?". A human re-reads their own command; an agent cannot, so
it either gives up or retries the identical query. search_jobs still always returns a list;
only the MCP boundary swaps in a diagnosis object, and only when that list is empty.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from openhire import service
from openhire.db import Application, Company, Job, init_db, session_scope


@pytest.fixture()
def tiny_index():
    init_db()
    now = dt.datetime.now(dt.timezone.utc)
    with session_scope() as s:
        for t in (Application, Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=now))
        for i, sk in enumerate([["rust", "k8s"], ["kubernetes operators"], ["python"]]):
            s.add(Job(
                id=f"acme:{i}", company_id="acme", title=f"Engineer {i}", location="Remote",
                remote_policy="remote", role_family="engineering", skills=sk,
                source="greenhouse", verified_at=now, first_seen_at=now, posted_at=now,
                apply_channel=f"https://boards.greenhouse.io/acme/{i}", content_hash=f"h{i}",
            ))
    yield


def test_unknown_tag_is_named_and_separated_from_a_dry_market(tiny_index):
    with session_scope() as s:
        d = service.diagnose_empty_search(s, required_skills=["notaskill_xyz"])
    assert d["results"] == [] and d["matched"] == 0
    assert d["unknown_skills"] == ["notaskill_xyz"]
    assert "does not exist in this index" in d["hint"]


def test_known_tags_report_a_genuine_miss_not_a_typo(tiny_index):
    with session_scope() as s:
        d = service.diagnose_empty_search(s, required_skills=["rust", "python"])
    assert d["unknown_skills"] == [], "both tags exist, so this is not a spelling problem"
    assert "genuinely has no live match" in d["hint"]
    assert "required_skills" in d["hint"], "the hint must name the strictest filter"


def test_substring_suggestion_points_at_the_real_tag(tiny_index):
    # The index tags "kubernetes operators", never plain "kubernetes" — fuzzy distance
    # would miss that, substring does not.
    with session_scope() as s:
        d = service.diagnose_empty_search(s, required_skills=["kubernetes"])
    assert "kubernetes operators" in d["suggestions"]["kubernetes"]


def test_nonsense_tag_gets_no_junk_suggestions(tiny_index):
    with session_scope() as s:
        d = service.diagnose_empty_search(s, required_skills=["zzzzqqqq_nope"])
    assert not d["suggestions"].get("zzzzqqqq_nope"), \
        "a tag with no real neighbour must return nothing rather than noise"


def test_filters_applied_is_echoed_back(tiny_index):
    with session_scope() as s:
        d = service.diagnose_empty_search(s, required_skills=["cobol"], role_family="engineering")
    assert d["filters_applied"]["role_family"] == "engineering"
    assert d["filters_applied"]["required_skills"] == ["cobol"]


def test_search_jobs_itself_still_always_returns_a_list(tiny_index):
    with session_scope() as s:
        assert service.search_jobs(s, required_skills=["notaskill_xyz"]) == []
