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
