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
    # ...and the hint must not point at suggestions that are not there.
    assert d["suggestions"] == {}
    assert "one of the suggestions" not in d["hint"]
    assert "drop the tag" in d["hint"]


def test_hint_points_at_suggestions_only_when_there_are_some(tiny_index):
    with session_scope() as s:
        d = service.diagnose_empty_search(s, required_skills=["kubernetes"])
    assert d["suggestions"]["kubernetes"]
    assert "retry with one of the suggestions" in d["hint"]


def test_unknown_company_hint_counts_employers_from_the_index_not_from_memory(tiny_index):
    """"It covers 139 employers" was literal text (rule 1 of the writing rules: numbers
    come from the index, never from memory). The number in the hint must be the number of
    employers with live postings in the index being searched."""
    import re

    from sqlalchemy import func

    with session_scope() as s:
        d = service.diagnose_empty_search(s, company="Nonexistent Robotics Co")
        expected = s.scalar(
            select(func.count(func.distinct(Job.company_id))).where(Job.delisted_at.is_(None))
        )
        assert service.live_employer_count(s) == expected == 1
    m = re.search(r"It covers (\d+) employer", d["hint"])
    assert m and int(m.group(1)) == expected, d["hint"]
    assert "139" not in d["hint"]


def test_filters_applied_is_echoed_back(tiny_index):
    with session_scope() as s:
        d = service.diagnose_empty_search(s, required_skills=["cobol"], role_family="engineering")
    assert d["filters_applied"]["role_family"] == "engineering"
    assert d["filters_applied"]["required_skills"] == ["cobol"]


def test_search_jobs_itself_still_always_returns_a_list(tiny_index):
    with session_scope() as s:
        assert service.search_jobs(s, required_skills=["notaskill_xyz"]) == []


# --- bootstrap progress (N2c from the round-2 tester report) ------------------

def test_bootstrap_passes_a_progress_callback_to_the_crawl():
    """The crawl runs 20+ minutes. `ingest` reported per-company progress; `bootstrap`
    called the same function without a callback and printed nothing for the whole run, so
    a first-time user could not tell work from a hang. Documenting the silence was the
    stopgap; passing the callback is the fix."""
    import inspect

    from openhire import cli

    src = inspect.getsource(cli.bootstrap)
    assert "_crawl_progress" in src, "bootstrap must define a progress callback"
    assert src.count("on_progress=_crawl_progress") == 2, (
        "both crawl paths (--fresh and the post-snapshot refresh) must report progress"
    )
    assert "run_ingest(respect_interval=False)" not in src, (
        "no crawl path may stay silent"
    )


def test_an_empty_index_says_so_instead_of_reporting_a_miss(tmp_path, monkeypatch):
    """A brand-new CLI user ran `ohp search` and got "无匹配结果。" — the same sentence
    they would get for a typo or for a role nobody is hiring for. The index was simply
    not downloaded yet. Every tag-level diagnosis below is also actively wrong on an
    empty index: with no rows to scan, every requested tag looks unknown and we would
    tell them to fix a spelling that was never wrong."""
    from openhire.db import session as session_mod
    from openhire import config

    monkeypatch.setattr(
        config, "DATABASE_URL", f"sqlite+pysqlite:///{(tmp_path / 'empty.db').as_posix()}"
    )
    session_mod.dispose_engine()
    try:
        session_mod.init_db()
        with session_mod.session_scope() as s:
            out = service.diagnose_empty_search(s, required_skills=["rust"])
        assert out["index_empty"] is True
        assert "bootstrap" in out["hint"]
        # It must NOT claim the tag is unknown: there was nothing to compare it against.
        assert not out.get("unknown_skills")
        assert not out.get("suggestions")
    finally:
        session_mod.dispose_engine()
