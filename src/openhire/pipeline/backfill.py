"""Backfill real ATS posting dates onto already-indexed jobs (P0-2).

The original ingest stored only our crawl time (first_seen_at); the ATS-provided posting
date was parsed then dropped, so datePosted and ghost_score were both anchored on the
crawl instant (datePosted faked to the crawl day; ghost_score stuck at 0). This re-fetches
every tenant from the public ATS — free, no LLM — and writes posted_at/updated_at onto the
matching rows, then recomputes ghost_score off the real posting age. It NEVER re-extracts
or touches skills/salary/remote (those are the DeepSeek values).
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select

from ..db import Company, Job, session_scope
from .crawler import CompanyRef, fetch_all
from .ghost_score import compute_ghost_score
from .ingest import _aware, _job_pk


@dataclass
class BackfillStats:
    companies_fetched: int = 0
    companies_failed: int = 0
    failed_tenants: list[str] = field(default_factory=list)
    jobs_dated: int = 0            # rows that got a real posted_at
    jobs_no_ats_date: int = 0      # matched but ATS exposed no date
    jobs_unmatched: int = 0        # indexed rows not present in the fresh fetch
    ghost_recomputed: int = 0


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def backfill_posting_dates(on_progress=None) -> BackfillStats:
    """Re-fetch all companies and write real posting dates + recomputed ghost_score."""
    now = _now()
    with session_scope() as session:
        companies = list(session.execute(select(Company)).scalars())
        refs = [CompanyRef(c.id, c.ats_vendor, c.ats_tenant, c.name) for c in companies]

    stats = BackfillStats()
    if not refs:
        return stats

    results = fetch_all_sync(refs, on_progress)

    with session_scope() as session:
        for cid, result in results.items():
            if not result.ok:
                stats.companies_failed += 1
                stats.failed_tenants.append(cid)
                continue
            stats.companies_fetched += 1
            # Map fresh ATS records by our job pk.
            fresh = {_job_pk(cid, r.ats_job_id): r for r in result.records}
            rows = list(
                session.execute(select(Job).where(Job.company_id == cid)).scalars()
            )
            for job in rows:
                rec = fresh.get(job.id)
                if rec is None:
                    stats.jobs_unmatched += 1
                elif rec.posted_at:
                    job.posted_at = _aware(rec.posted_at)
                    job.updated_at = _aware(rec.updated_at) if rec.updated_at else None
                    stats.jobs_dated += 1
                else:
                    stats.jobs_no_ats_date += 1
                # Recompute ghost_score for every live row off the real posting age.
                if job.delisted_at is None:
                    anchor = _aware(job.posted_at) if job.posted_at else _aware(job.first_seen_at)
                    job.ghost_score = compute_ghost_score(job.relist_count, anchor, now)
                    stats.ghost_recomputed += 1
            if on_progress:
                on_progress("ingest", cid, result)
    return stats


def fetch_all_sync(refs, on_progress=None):
    def _cb(company, result):
        if on_progress:
            on_progress("fetch", company.id, result)

    return asyncio.run(fetch_all(refs, on_result=_cb))
