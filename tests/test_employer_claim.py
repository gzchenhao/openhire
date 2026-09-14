"""Employer claim → response_sla_days. The protocol's one employer-declared field.

Why it was null from 0.1 to 0.5, and why that was never a bug: we cannot observe a reply.
The application deep-links to the employer's own site and never touches this server
(`Application.delivered_via` is always "employer_site", and the table carries no PII by a
CI-enforced rule), so response time is structurally unmeasurable from here. Inferring it
would mean either handling the application or handling the reply — both cross the first
privacy red line. The only honest source is the employer saying it themselves.

What was actually missing was the place to put the answer when one arrives.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from openhire import service
from openhire.db import Application, Company, Job, init_db, session_scope

NOW = dt.datetime(2026, 9, 14, tzinfo=dt.timezone.utc)


@pytest.fixture()
def seeded():
    init_db()
    with session_scope() as s:
        for t in (Application, Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add_all([
            Company(id="claimed", name="Claimed Co", ats_vendor="greenhouse", ats_tenant="c"),
            Company(id="unclaimed", name="Unclaimed Co", ats_vendor="greenhouse", ats_tenant="u"),
        ])
        for cid in ("claimed", "unclaimed"):
            s.add(Job(
                id=f"{cid}:1", company_id=cid, title="Engineer", location="Remote",
                remote_policy="remote", skills=["python"], role_family="engineering",
                source="ats_public_api", first_seen_at=NOW, posted_at=NOW,
                verified_at=NOW, apply_channel=f"https://x.test/{cid}", content_hash=cid,
            ))
        s.flush()
    yield


def _sla(company_id: str) -> int | None:
    with session_scope() as s:
        return service.search_jobs(s, company=company_id, now=NOW, limit=1)[0]["response_sla_days"]


def test_unclaimed_employer_reports_null_not_a_guess(seeded):
    assert _sla("unclaimed") is None


def test_claim_declares_the_window_for_that_employers_postings(seeded):
    with session_scope() as s:
        c = s.get(Company, "claimed")
        c.verified, c.response_sla_days, c.claimed_at = True, 7, NOW
    assert _sla("claimed") == 7
    assert _sla("unclaimed") is None, "a claim must not leak to anyone else"


def test_the_declaration_lives_on_the_company_so_later_roles_inherit_it(seeded):
    """It is stored per-employer, not per-posting, so it survives a re-crawl and covers
    roles posted after the claim without anyone re-applying it."""
    with session_scope() as s:
        c = s.get(Company, "claimed")
        c.verified, c.response_sla_days = True, 3
        s.add(Job(
            id="claimed:new", company_id="claimed", title="Later Hire", location="Remote",
            remote_policy="remote", skills=["python"], role_family="engineering",
            source="ats_public_api", first_seen_at=NOW, posted_at=NOW, verified_at=NOW,
            apply_channel="https://x.test/new", content_hash="new",
        ))
        s.flush()
        rows = service.search_jobs(s, company="claimed", now=NOW, limit=10)
    assert len(rows) == 2
    assert {r["response_sla_days"] for r in rows} == {3}


def test_a_per_posting_value_still_wins(seeded):
    with session_scope() as s:
        s.get(Company, "claimed").response_sla_days = 7
        s.get(Job, "claimed:1").response_sla_days = 2
        s.flush()
        assert service.search_jobs(s, company="claimed", now=NOW)[0]["response_sla_days"] == 2


def test_withdrawing_a_claim_clears_it(seeded):
    with session_scope() as s:
        c = s.get(Company, "claimed")
        c.verified, c.response_sla_days, c.claimed_at = True, 7, NOW
    assert _sla("claimed") == 7
    with session_scope() as s:
        c = s.get(Company, "claimed")
        c.verified, c.response_sla_days, c.claimed_at = False, None, None
    assert _sla("claimed") is None


def test_claiming_cannot_touch_rank(seeded):
    """The red line: a claim buys a badge and a declaration, never a position."""
    import inspect

    from openhire import cli

    # Check the code, not the prose: the docstring says the words "match, freshness"
    # precisely to promise it does not touch them, and grepping the whole source would
    # fail on its own disclaimer.
    src = inspect.getsource(cli.claim)
    body = src.replace(cli.claim.__doc__ or "", "")
    for forbidden in ("rank_score", "match_quality", "freshness", "ghost_score"):
        assert forbidden not in body, f"the claim path must never touch {forbidden}"
