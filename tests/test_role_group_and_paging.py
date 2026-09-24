"""role_group + offset: the two signals an agent needs to spend its budget well.

Employers list one role once per city. Those rows are genuinely distinct (own job_id, own
apply_channel) so we never collapse them server-side, but nothing in the payload used to say
they were siblings — a client agent had to guess from string equality, and ~20% of every
`limit` it asked for went to rows it already had, with no way to ask for "more, but
different". role_group supplies the grouping key; offset supplies the escape hatch.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from openhire import service
from openhire.db import Application, Company, Job, init_db, session_scope


def _seed(s, n_cities: int = 3) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    for t in (Application, Job, Company):
        for row in s.execute(select(t)).scalars():
            s.delete(row)
    s.flush()
    s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme",
                  careers_url="x", last_crawled_at=now))
    for i, city in enumerate(["Austin", "Dublin", "Tokyo"][:n_cities]):
        s.add(Job(
            id=f"acme:same{i}", company_id="acme", title="Staff Platform Engineer",
            location=city, remote_policy="remote", role_family="engineering",
            skills=["k8s"], source="greenhouse", verified_at=now, first_seen_at=now,
            posted_at=now, apply_channel=f"https://boards.greenhouse.io/acme/{i}",
            content_hash=f"h-same-{i}",
        ))
    for i in range(4):
        s.add(Job(
            id=f"acme:other{i}", company_id="acme", title=f"Distinct Role {i}",
            location="Remote", remote_policy="remote", role_family="engineering",
            skills=["k8s"], source="greenhouse", verified_at=now, first_seen_at=now,
            posted_at=now, apply_channel=f"https://boards.greenhouse.io/acme/o{i}",
            content_hash=f"h-other-{i}",
        ))
    s.flush()


@pytest.fixture()
def seeded():
    init_db()
    with session_scope() as s:
        _seed(s)
    yield


def test_same_role_across_cities_shares_a_role_group(seeded):
    with session_scope() as s:
        rows = service.search_jobs(s, skills=["k8s"], limit=50)
        same = [r for r in rows if r["title"] == "Staff Platform Engineer"]
        assert len(same) == 3, "the three city rows must all survive — we never collapse"
        assert len({r["role_group"] for r in same}) == 1, "siblings must share one role_group"
        # ...and they must stay individually applicable.
        assert len({r["job_id"] for r in same}) == 3
        assert len({r["apply_channel"] for r in same}) == 3


def test_distinct_roles_get_distinct_groups(seeded):
    with session_scope() as s:
        rows = service.search_jobs(s, skills=["k8s"], limit=50)
        distinct = [r for r in rows if r["title"].startswith("Distinct Role")]
        assert len({r["role_group"] for r in distinct}) == len(distinct)


def test_role_group_normalises_case_and_whitespace_but_not_company():
    a = service.role_group("acme", "Staff Platform Engineer")
    assert a == service.role_group("acme", "  staff   PLATFORM engineer ")
    assert a != service.role_group("globex", "Staff Platform Engineer")


def test_offset_pages_without_overlap_and_terminates(seeded):
    with session_scope() as s:
        first = service.search_jobs(s, skills=["k8s"], limit=3, offset=0)
        second = service.search_jobs(s, skills=["k8s"], limit=3, offset=3)
        assert len(first) == 3
        assert not ({r["job_id"] for r in first} & {r["job_id"] for r in second}), \
            "a second page must not repeat the first"
        # 7 seeded rows: the third page is short, which is how an agent detects the end.
        assert len(service.search_jobs(s, skills=["k8s"], limit=3, offset=6)) < 3


def test_offset_is_clamped_not_fatal(seeded):
    with session_scope() as s:
        assert service.search_jobs(s, skills=["k8s"], limit=3, offset=-5), \
            "a negative offset must clamp to 0, not empty the result"
        assert service.search_jobs(s, skills=["k8s"], limit=3, offset=10_000) == []


# --- collapse_role_group (N5 from the round-2 tester report) ------------------
# The grouping key alone made every caller pay to do the same fold. This makes the
# fold a server-side option, without ever hiding the sibling rows from a caller
# who needs them (location and visa constraints make each city row real).

def test_collapse_keeps_one_row_per_group_and_counts_the_rest(seeded):
    with session_scope() as s:
        full = service.search_jobs(s, skills=["k8s"], limit=50)
        folded = service.search_jobs(s, skills=["k8s"], limit=50, collapse_role_group=True)
        assert len(full) == 7, "seed: 3 city rows + 4 distinct"
        assert len(folded) == 5, "the 3 city rows fold into 1"
        same = [r for r in folded if r["title"] == "Staff Platform Engineer"]
        assert len(same) == 1 and same[0]["role_group_size"] == 3


def test_collapse_is_off_by_default(seeded):
    with session_scope() as s:
        rows = service.search_jobs(s, skills=["k8s"], limit=50)
        assert all("role_group_size" not in r for r in rows)


def test_collapsed_row_still_carries_its_group_key(seeded):
    """A caller that folded and then needs every city must be able to ask again."""
    with session_scope() as s:
        folded = service.search_jobs(s, skills=["k8s"], limit=50, collapse_role_group=True)
        assert all(r.get("role_group") for r in folded)


def test_asking_for_more_than_a_page_says_so_instead_of_looking_complete(seeded):
    """Round 7: a reviewer ran `company=XPeng limit=200`, got 100 of 198 with no notice,
    and concluded the index held 100 XPeng jobs. A skill search then surfaced two XPeng
    roles that were "not in the full list" — the same silent cut, read as a consistency
    bug. `offset` reached the rest; nothing said to page."""
    from openhire import mcp_server, service

    assert service.MAX_PAGE_SIZE == 100

    # Seven rows match. Round 8: this came back `truncated: true` with 92 rows and sent
    # the client to an empty page 2. Fewer rows than the page size means there is no more.
    out = mcp_server.search_jobs(limit=200)
    assert isinstance(out, dict), "an over-cap request must not look like a complete list"
    assert out["truncated"] is False
    assert out["page_size"] == service.MAX_PAGE_SIZE
    assert out["requested_limit"] == 200
    assert "offset=" not in out["hint"] and "no next page" in out["hint"]
    assert len(out["results"]) == 7

    # A full page is the one case where there MAY be more, and only then does the hint
    # point at the next offset.
    with session_scope() as s:
        now = dt.datetime.now(dt.timezone.utc)
        for i in range(service.MAX_PAGE_SIZE):
            s.add(Job(
                id=f"acme:bulk{i}", company_id="acme", title=f"Bulk Role {i}",
                location="Remote", remote_policy="remote", role_family="engineering",
                skills=["k8s"], source="greenhouse", verified_at=now, first_seen_at=now,
                posted_at=now, apply_channel=f"https://boards.greenhouse.io/acme/b{i}",
                content_hash=f"h-bulk-{i}",
            ))
    out = mcp_server.search_jobs(limit=200)
    assert out["truncated"] is True
    assert len(out["results"]) == service.MAX_PAGE_SIZE
    assert "offset=100" in out["hint"]
    # Folding siblings must not make a full page look short: the page still stands for
    # 100 fetched rows even when fewer groups are shown.
    folded = mcp_server.search_jobs(limit=200, collapse_role_group=True)
    assert folded["truncated"] is True
    assert sum(r["role_group_size"] for r in folded["results"]) == service.MAX_PAGE_SIZE

    # A request inside the cap keeps the plain list shape every client already expects.
    inside = mcp_server.search_jobs(limit=5)
    assert isinstance(inside, list)
