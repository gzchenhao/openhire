"""Seed the `companies` table by verifying candidate tenants live.

Per README §数据源: a tenant slug MUST be validated at runtime — only tenants that
currently return HTTP 200 with a jobs array are inserted (`verified` stays False; that
column is reserved for v0.3 employer claim, distinct from tenant validity).
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select

from ..ats import get_client
from ..db import Company, session_scope
from ..seed import all_candidates
from .crawler import CompanyRef, fetch_all


@dataclass
class SeedStats:
    verified: int = 0
    rejected: int = 0
    total_jobs: int = 0
    inserted: int = 0
    rejected_tenants: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.rejected_tenants is None:
            self.rejected_tenants = []


def seed_companies(on_result=None) -> SeedStats:
    """Validate every seed candidate and upsert the ones that pass."""
    candidates = all_candidates()
    # Reuse the crawler's concurrency + politeness by treating candidates as refs.
    # `id` is OUR slug and `ats_tenant` is the board to fetch — identical for most
    # companies, deliberately different for one that migrated ATS (see Candidate.slug).
    refs = [
        CompanyRef(id=c.slug, ats_vendor=c.vendor, ats_tenant=c.tenant, name=c.name)
        for c in candidates
    ]
    by_slug = {c.slug: c for c in candidates}

    results = asyncio.run(fetch_all(refs, on_result=on_result))

    stats = SeedStats()
    now = dt.datetime.now(dt.timezone.utc)
    with session_scope() as session:
        for slug, result in results.items():
            cand = by_slug[slug]
            if not (result.ok and result.count > 0):
                stats.rejected += 1
                stats.rejected_tenants.append(f"{cand.vendor}:{slug}")
                continue

            stats.verified += 1
            stats.total_jobs += result.count
            client = get_client(cand.vendor)
            company = session.get(Company, slug)
            if company is None:
                company = Company(
                    id=slug,
                    name=cand.name,
                    ats_vendor=cand.vendor,
                    ats_tenant=cand.tenant,
                    careers_url=client.careers_url(cand.tenant),
                    verified=False,
                )
                session.add(company)
                stats.inserted += 1
            else:
                # Re-point an existing employer at its current board without touching
                # `companies.id`, so the job history stays attached to the same row.
                company.name = cand.name
                company.ats_vendor = cand.vendor
                company.ats_tenant = cand.tenant
                company.careers_url = client.careers_url(cand.tenant)

        apply_claims(session)
    return stats


def apply_claims(session) -> int:
    """Make the DB match `seed/claims.py`. Declarative: an entry deleted there is withdrawn
    here. Runs inside `ohp seed`, which CI runs weekly, so a claim survives every rebuild
    without anyone remembering to re-apply it.

    Never touches ranking. A claim sets `verified`, the employer's declared reply window,
    and the date — nothing that could move a posting up a page.
    """
    from ..seed.claims import CLAIMS

    claimed = {c.company_id: c for c in CLAIMS}
    applied = 0
    for company in session.execute(select(Company)).scalars():
        claim = claimed.get(company.id)
        if claim is None:
            if company.verified or company.response_sla_days is not None or company.claimed_at:
                company.verified = False
                company.response_sla_days = None
                company.claimed_at = None
            continue
        company.verified = True
        company.response_sla_days = claim.response_sla_days
        company.claimed_at = dt.datetime.combine(
            claim.claimed_on, dt.time.min, tzinfo=dt.timezone.utc
        )
        applied += 1
    return applied
