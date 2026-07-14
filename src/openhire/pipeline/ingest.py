"""The ingest pipeline — turns fetched ATS jobs into the durable index.

Per README §管线逻辑:
  1. ingest loop by freshness tier
  2. change detection via content_hash (unchanged → only refresh verified_at)
  3. LLM extraction ONLY on hash change (or new job)
  4. delist detection — vanished jobs get delisted_at set (row is never deleted)
  5. relist detection — a new job whose normalized title matches a delisted sibling
     inherits first_seen_at and increments relist_count
  6. ghost_score recomputed every crawl (it grows with staleness)
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..ats import FetchResult, JobRecord, get_client
from ..db import Company, Job, session_scope
from .crawler import CompanyRef, fetch_all
from .extract import Extractor, get_extractor
from .ghost_score import compute_ghost_score
from .hashing import content_hash, normalize_title

SOURCE_ATS = "ats_public_api"  # protocol field ②


@dataclass
class IngestStats:
    companies_crawled: int = 0
    companies_failed: int = 0
    failed_tenants: list[str] = field(default_factory=list)
    jobs_new: int = 0
    jobs_updated: int = 0
    jobs_unchanged: int = 0
    jobs_delisted: int = 0
    jobs_relisted: int = 0
    extractions: int = 0

    @property
    def jobs_seen(self) -> int:
        return self.jobs_new + self.jobs_updated + self.jobs_unchanged


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _job_pk(company_id: str, ats_job_id: str) -> str:
    return f"{company_id}:{ats_job_id}"


# --- Freshness tiers ----------------------------------------------------------
def is_company_hot(session: Session, company_id: str, now: dt.datetime) -> bool:
    """Hot = something changed in the last FRESHNESS_HOT_WINDOW_DAYS days."""
    window = now - dt.timedelta(days=config.FRESHNESS_HOT_WINDOW_DAYS)
    stmt = select(Job.id).where(
        Job.company_id == company_id,
        (Job.first_seen_at >= window) | (Job.delisted_at >= window),
    ).limit(1)
    return session.execute(stmt).first() is not None


def due_companies(session: Session, now: dt.datetime | None = None) -> list[Company]:
    """Companies whose last_crawled_at is older than their tier interval, honoring the
    30-minute per-tenant floor."""
    now = now or _now()
    floor = dt.timedelta(minutes=config.MIN_TENANT_INTERVAL_MINUTES)
    hot_iv = dt.timedelta(hours=config.FRESHNESS_HOT_INTERVAL_HOURS)
    cold_iv = dt.timedelta(hours=config.FRESHNESS_COLD_INTERVAL_HOURS)

    due: list[Company] = []
    for company in session.execute(select(Company)).scalars():
        last = company.last_crawled_at
        if last is None:
            due.append(company)
            continue
        last = _aware(last)
        if now - last < floor:
            continue  # politeness: never within 30 min
        interval = hot_iv if is_company_hot(session, company.id, now) else cold_iv
        if now - last >= interval:
            due.append(company)
    return due


def _aware(d: dt.datetime) -> dt.datetime:
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


# --- Per-company ingest -------------------------------------------------------
def ingest_company(
    session: Session,
    company: Company,
    result: FetchResult,
    extractor: Extractor,
    stats: IngestStats,
    now: dt.datetime | None = None,
) -> None:
    now = now or _now()
    if not result.ok:
        stats.companies_failed += 1
        stats.failed_tenants.append(f"{company.ats_vendor}:{company.ats_tenant}")
        return

    stats.companies_crawled += 1

    # Load existing jobs for this company once.
    existing: dict[str, Job] = {
        j.id: j
        for j in session.execute(
            select(Job).where(Job.company_id == company.id)
        ).scalars()
    }
    seen_ids: set[str] = set()

    for rec in result.records:
        pk = _job_pk(company.id, rec.ats_job_id)
        seen_ids.add(pk)
        chash = content_hash(rec.title, rec.description_raw)
        job = existing.get(pk)

        if job is None:
            _insert_new_job(session, company, rec, pk, chash, extractor, stats, now, existing)
        else:
            _update_job(job, rec, chash, extractor, stats, now)

    # Delist detection: previously-live jobs not seen this crawl.
    for pk, job in existing.items():
        if pk not in seen_ids and job.delisted_at is None:
            job.delisted_at = now
            stats.jobs_delisted += 1

    # Recompute ghost_score for every live job (staleness grows over time), aged off the
    # real posting date when known.
    for job in existing.values():
        if job.delisted_at is None:
            anchor = _aware(job.posted_at) if job.posted_at else _aware(job.first_seen_at)
            job.ghost_score = compute_ghost_score(job.relist_count, anchor, now)

    company.last_crawled_at = now
    if company.name and result.records:
        pass  # name is authoritative from seed; ATS payloads vary


def _insert_new_job(
    session: Session,
    company: Company,
    rec: JobRecord,
    pk: str,
    chash: str,
    extractor: Extractor,
    stats: IngestStats,
    now: dt.datetime,
    existing: dict[str, Job],
) -> None:
    """Insert a brand-new job id, applying relist inheritance if applicable."""
    first_seen = now
    relist_count = 0

    # Relist detection: same company, same normalized title, an existing DELISTED sibling.
    norm = normalize_title(rec.title)
    if norm:
        best = None
        for other in existing.values():
            if other.delisted_at is not None and normalize_title(other.title) == norm:
                if best is None or _aware(other.delisted_at) > _aware(best.delisted_at):
                    best = other
        if best is not None:
            relist_count = best.relist_count + 1
            first_seen = _aware(best.first_seen_at)
            stats.jobs_relisted += 1

    extraction = extractor.extract(rec)
    stats.extractions += 1

    # ghost_score ages off the real posting date when the ATS provides one.
    age_anchor = _aware(rec.posted_at) if rec.posted_at else first_seen
    job = Job(
        id=pk,
        company_id=company.id,
        title=rec.title,
        description_raw=rec.description_raw,
        skills=extraction.skills,
        remote_policy=extraction.remote_policy,
        salary_min=extraction.salary_min,
        salary_max=extraction.salary_max,
        salary_currency=extraction.salary_currency,
        salary_inferred=False,  # v0.1 never infers
        location=rec.location,
        posted_at=_aware(rec.posted_at) if rec.posted_at else None,  # real ATS date
        updated_at=_aware(rec.updated_at) if rec.updated_at else None,
        first_seen_at=first_seen,
        verified_at=now,  # protocol field ①
        delisted_at=None,
        relist_count=relist_count,
        ghost_score=compute_ghost_score(relist_count, age_anchor, now),  # ③
        response_sla_days=None,  # ④ — always NULL in v0.1
        source=SOURCE_ATS,  # ②
        apply_channel=rec.apply_channel,  # ⑤
        content_hash=chash,
    )
    session.add(job)
    existing[pk] = job
    stats.jobs_new += 1


def _update_job(
    job: Job,
    rec: JobRecord,
    chash: str,
    extractor: Extractor,
    stats: IngestStats,
    now: dt.datetime,
) -> None:
    """Refresh an existing job. Re-extract only when the content hash changed."""
    job.verified_at = now  # protocol field ① — confirmed live again
    job.apply_channel = rec.apply_channel or job.apply_channel
    # Keep the real ATS posting dates fresh (posted_at is stable; updated_at moves).
    if rec.posted_at:
        job.posted_at = _aware(rec.posted_at)
    if rec.updated_at:
        job.updated_at = _aware(rec.updated_at)

    if job.delisted_at is not None:
        # Same id reappeared at source → it is live again (not a relist).
        job.delisted_at = None

    if job.content_hash == chash:
        stats.jobs_unchanged += 1
        return

    # Content changed → re-extract.
    extraction = extractor.extract(rec)
    stats.extractions += 1
    job.title = rec.title
    job.description_raw = rec.description_raw
    job.skills = extraction.skills
    job.remote_policy = extraction.remote_policy
    job.salary_min = extraction.salary_min
    job.salary_max = extraction.salary_max
    job.salary_currency = extraction.salary_currency
    job.location = rec.location
    job.content_hash = chash
    stats.jobs_updated += 1


# --- Orchestration ------------------------------------------------------------
def run_ingest(
    company_ids: list[str] | None = None,
    respect_interval: bool = True,
    on_progress=None,
) -> IngestStats:
    """Crawl due (or specified) companies and ingest. Synchronous entry point."""
    now = _now()
    with session_scope() as session:
        if company_ids:
            companies = list(
                session.execute(
                    select(Company).where(Company.id.in_(company_ids))
                ).scalars()
            )
        elif respect_interval:
            companies = due_companies(session, now)
        else:
            companies = list(session.execute(select(Company)).scalars())

        refs = [
            CompanyRef(c.id, c.ats_vendor, c.ats_tenant, c.name) for c in companies
        ]
        by_id = {c.id: c for c in companies}

    stats = IngestStats()
    if not refs:
        return stats

    def _on_fetch(company_ref, result):
        if on_progress:
            on_progress("fetch", company_ref, result)

    results = asyncio.run(fetch_all(refs, on_result=_on_fetch))

    extractor = get_extractor()
    # Write phase — one session; ingest each company transactionally-ish.
    with session_scope() as session:
        for cid, result in results.items():
            company = session.get(Company, cid)
            if company is None:
                continue
            ingest_company(session, company, result, extractor, stats, now)
            if on_progress:
                on_progress("ingest", by_id.get(cid), result)

    return stats
