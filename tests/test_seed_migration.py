"""ATS migrations: the board slug may move, our company slug must not.

Aurora and Temporal left Greenhouse for Ashby and Fireworks AI's Ashby board was
renamed (all three boards 404'd for five weeks before this was noticed). Re-seeding
them under their new tenant as a NEW company row would strand every job we ever
recorded for them, because a job PK is `{company_id}:{ats_job_id}`. So `companies.id`
is pinned and only `ats_vendor` / `ats_tenant` / `careers_url` move.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from openhire.db import Company, Job, init_db, session_scope
from openhire.pipeline import seed_runner
from openhire.ats.base import FetchResult, JobRecord
from openhire.seed import Candidate, all_candidates, candidate_count

UTC = dt.timezone.utc

def _rec(jid: str) -> JobRecord:
    return JobRecord(ats_job_id=jid, title="t", description_raw="d",
                     apply_channel="https://x", location=None, remote_hint=None)


def _fake_fetch(n: int):
    """`seed_companies` drives fetch_all through asyncio.run, so the stub is async."""
    async def fetch_all(refs, on_result=None):
        return {
            r.id: FetchResult(ok=True, status=200,
                              records=[_rec(str(i)) for i in range(n)])
            for r in refs
        }
    return fetch_all


MIGRATED = {
    "aurorainnovation": ("ashby", "aurora-operations-inc"),
    "temporaltechnologies": ("ashby", "temporal"),
    "fireworksai": ("ashby", "fireworks"),
}


def test_candidate_slug_defaults_to_tenant():
    c = Candidate(vendor="greenhouse", tenant="anthropic", name="Anthropic")
    assert c.slug == "anthropic"


def test_candidate_slug_pins_history_when_the_board_moves():
    c = Candidate(vendor="ashby", tenant="temporal", name="Temporal",
                  company_id="temporaltechnologies")
    assert c.slug == "temporaltechnologies" and c.tenant == "temporal"


def test_migrated_boards_are_seeded_under_their_original_slug():
    by_slug = {c.slug: c for c in all_candidates()}
    for slug, (vendor, tenant) in MIGRATED.items():
        assert slug in by_slug, f"{slug} lost its company slug"
        assert (by_slug[slug].vendor, by_slug[slug].tenant) == (vendor, tenant)


def test_dead_greenhouse_boards_are_gone():
    tenants = {(c.vendor, c.tenant) for c in all_candidates()}
    assert ("greenhouse", "aurorainnovation") not in tenants
    assert ("greenhouse", "temporaltechnologies") not in tenants
    # The old Ashby slug is gone too — the board was renamed, not duplicated.
    assert ("ashby", "fireworksai") not in tenants


def test_no_duplicate_company_slugs():
    slugs = [c.slug for c in all_candidates()]
    assert len(slugs) == len(set(slugs)) == candidate_count()


def test_seed_repoints_an_existing_company_without_changing_its_id(monkeypatch):
    """The regression that matters: re-seeding a migrated company keeps its jobs."""
    init_db()
    now = dt.datetime.now(UTC)
    with session_scope() as s:
        for t in (Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="temporaltechnologies", name="Temporal",
                      ats_vendor="greenhouse", ats_tenant="temporaltechnologies",
                      careers_url="https://job-boards.greenhouse.io/temporaltechnologies",
                      last_crawled_at=now))
        s.add(Job(id="temporaltechnologies:12345", company_id="temporaltechnologies",
                  title="Old Greenhouse posting", description_raw="", skills=[],
                  remote_policy="remote", first_seen_at=now, verified_at=now,
                  source="ats_public_api", apply_channel="https://x",
                  content_hash="h1", ghost_score=0.0, extraction_source="deepseek"))

    cand = Candidate(vendor="ashby", tenant="temporal", name="Temporal",
                     company_id="temporaltechnologies")
    monkeypatch.setattr(seed_runner, "all_candidates", lambda: [cand])
    monkeypatch.setattr(seed_runner, "fetch_all", _fake_fetch(57))

    stats = seed_runner.seed_companies()
    assert stats.verified == 1 and stats.inserted == 0  # updated, not re-created

    with session_scope() as s:
        co = s.get(Company, "temporaltechnologies")
        assert co is not None
        assert (co.ats_vendor, co.ats_tenant) == ("ashby", "temporal")
        assert co.careers_url == "https://jobs.ashbyhq.com/temporal"
        # The history survived: same row, same job PKs.
        assert s.scalar(select(Job.id).where(Job.company_id == "temporaltechnologies")) \
            == "temporaltechnologies:12345"


def test_seed_inserts_a_new_company_at_its_ats_tenant(monkeypatch):
    """The ordinary case is unchanged: slug == tenant."""
    init_db()
    with session_scope() as s:
        for row in s.execute(select(Company)).scalars():
            s.delete(row)

    cand = Candidate(vendor="ashby", tenant="openai", name="OpenAI")
    monkeypatch.setattr(seed_runner, "all_candidates", lambda: [cand])
    monkeypatch.setattr(seed_runner, "fetch_all", _fake_fetch(3))
    stats = seed_runner.seed_companies()
    assert stats.inserted == 1
    with session_scope() as s:
        co = s.get(Company, "openai")
        assert (co.id, co.ats_tenant) == ("openai", "openai")
