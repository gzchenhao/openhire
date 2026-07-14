"""One-shot maintenance: regenerate every job's apply_channel with the deep-link
resolver, and report which companies use employer-embedded (non-ATS-host) apply URLs.

This recomputes deterministically from (vendor, tenant, ats_job_id, current stored URL) —
no re-fetch needed, since the resolver's decision only needs the vendor URL and the ids.
After the ATS clients were fixed, fresh crawls already produce correct URLs; this repairs
rows ingested before the fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from ..ats import resolve_apply_channel
from ..db import Company, Job, session_scope


@dataclass
class RegenStats:
    jobs_total: int = 0
    jobs_rewritten: int = 0
    jobs_fallback: int = 0  # rows now using a canonical ATS URL
    embed_companies: list[str] = field(default_factory=list)
    embed_jobs: int = 0


def regenerate_apply_channels() -> RegenStats:
    stats = RegenStats()
    embed = set()
    with session_scope() as session:
        companies = {c.id: c for c in session.execute(select(Company)).scalars()}
        for job in session.execute(select(Job)).scalars():
            stats.jobs_total += 1
            company = companies.get(job.company_id)
            if company is None:
                continue
            ats_job_id = job.id.split(":", 1)[1]
            res = resolve_apply_channel(
                company.ats_vendor, company.ats_tenant, ats_job_id, job.apply_channel
            )
            if res.is_embed:
                embed.add(company.id)
                stats.embed_jobs += 1
            if res.used_fallback:
                stats.jobs_fallback += 1
            if res.url != job.apply_channel:
                job.apply_channel = res.url
                stats.jobs_rewritten += 1
    stats.embed_companies = sorted(embed)
    return stats
