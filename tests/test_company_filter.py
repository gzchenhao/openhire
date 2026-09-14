"""The company filter — N1 from the round-2 tester report.

The gap it closes: "what is Unitree hiring?" is the first question a user asks after
installing, and until now the product could not answer it — the tester got his answer by
opening the SQLite file and writing SQL by hand.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from openhire import service
from openhire.db import Application, Company, Job, init_db, session_scope

NOW = dt.datetime(2026, 9, 14, tzinfo=dt.timezone.utc)


def _seed(s) -> None:
    for t in (Application, Job, Company):
        for row in s.execute(select(t)).scalars():
            s.delete(row)
    s.flush()
    s.add_all([
        Company(id="unitree", name="宇树科技 Unitree", ats_vendor="beisen", ats_tenant="unitree"),
        Company(id="xpeng", name="小鹏汽车 XPeng", ats_vendor="moka", ats_tenant="xpeng"),
        Company(id="waymo", name="Waymo", ats_vendor="greenhouse", ats_tenant="waymo"),
    ])
    for i, (cid, title) in enumerate([
        ("unitree", "Motion Control Engineer"),
        ("unitree", "Perception Engineer"),
        ("xpeng", "Planning Engineer"),
        ("waymo", "Simulation Engineer"),
    ]):
        s.add(Job(
            id=f"{cid}:{i}", company_id=cid, title=title, location="Remote",
            remote_policy="remote", skills=["python"], role_family="engineering",
            source="greenhouse", verified_at=NOW, first_seen_at=NOW, posted_at=NOW,
            apply_channel=f"https://example.test/{cid}/{i}", content_hash=f"h{i}",
        ))
    s.flush()


@pytest.fixture()
def seeded():
    init_db()
    with session_scope() as s:
        _seed(s)
    yield


def test_resolves_by_id_name_fragment_and_language(seeded):
    with session_scope() as s:
        for query in ("unitree", "Unitree", "UNITREE", "宇树", "宇树科技"):
            assert [c.id for c in service.resolve_company(s, query)] == ["unitree"], query


def test_exact_hit_beats_substring(seeded):
    """A company whose whole name is a substring of another must not be drowned by it."""
    with session_scope() as s:
        s.add(Company(id="way", name="Way", ats_vendor="lever", ats_tenant="way"))
        s.flush()
        assert [c.id for c in service.resolve_company(s, "Way")] == ["way"]
        assert {c.id for c in service.resolve_company(s, "wa")} == {"way", "waymo"}


def test_search_restricts_to_that_employer(seeded):
    with session_scope() as s:
        rows = service.search_jobs(s, company="宇树", now=NOW, limit=10)
        assert len(rows) == 2
        assert {r["company_id"] for r in rows} == {"unitree"}


def test_unknown_company_returns_nothing_not_everything(seeded):
    """The failure that would matter: an unmatched name falling through to an unfiltered
    search, which reads as a plausible answer to a question nobody asked."""
    with session_scope() as s:
        assert service.search_jobs(s, company="no-such-employer", now=NOW) == []


def test_diagnosis_names_the_company_not_the_tags(seeded):
    with session_scope() as s:
        out = service.diagnose_empty_search(s, company="Rivian")
        assert out["matched"] == 0
        assert out["unknown_companies"] == ["Rivian"]
        assert "no company matching" in out["hint"]
        assert out["filters_applied"]["company"] == "Rivian"


def test_known_company_with_no_match_is_a_different_answer(seeded):
    with session_scope() as s:
        out = service.diagnose_empty_search(s, company="Waymo", skills=["python"])
        assert "unknown_companies" not in out
        assert "is in the index" in out["hint"]


def test_company_composes_with_other_filters(seeded):
    with session_scope() as s:
        assert service.search_jobs(s, company="unitree", role_family="sales", now=NOW) == []
