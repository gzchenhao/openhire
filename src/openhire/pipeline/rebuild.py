"""Re-run JD extraction with an LLM backend (default DeepSeek), safely.

Design constraints from the user:
  * Cheapest model, simple task — DeepSeek deepseek-chat.
  * Sample first: `run_sample_comparison(100)` compares LLM vs heuristic, no DB writes.
  * Budget: track real token spend; HARD STOP at a CNY ceiling (default ¥50).
  * Resumable: commit per batch; rows already at the target source are skipped on re-run.
  * Rollback column: the prior heuristic values are copied into *_fallback before overwrite.
"""

from __future__ import annotations

import concurrent.futures as cf
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..ats.base import JobRecord
from ..db import Job, session_scope
from ..db.migrate import ensure_schema
from .extract import DeepSeekExtractor, make_deepseek_extractor

TARGET_SOURCE = "deepseek"


def cost_cny(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens / 1_000_000 * config.DEEPSEEK_PRICE_INPUT_CNY
        + completion_tokens / 1_000_000 * config.DEEPSEEK_PRICE_OUTPUT_CNY
    )


def _job_to_record(job: Job) -> JobRecord:
    # LLM reads title + JD for SKILLS. remote/salary hints are passed so the merge can
    # keep authoritative ATS values (LLM only fills gaps) — see merge_extraction.
    return JobRecord(
        ats_job_id=job.id.split(":", 1)[1],
        title=job.title,
        description_raw=job.description_raw or "",
        apply_channel=job.apply_channel,
        location=job.location,
        remote_hint=None,
    )


@dataclass
class MergedValues:
    skills: list[str]
    remote_policy: str
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None


def merge_extraction(job: Job, oc: "_JobOutcome") -> MergedValues:
    """Combine LLM skills with the existing authoritative ATS-derived remote/salary.

    Policy (avoids the regressions the raw sample revealed):
      * skills   → always the LLM's (its clear win; catches roles the heuristic missed)
      * remote   → keep the existing ATS-derived value; only use the LLM when ours is
                   'unknown' (so the LLM fills gaps, never overrides first-party data)
      * salary   → keep the existing (ATS-structured / heuristic) value; only use the
                   LLM's when we have none (LLM salary is unreliable under JD truncation)
    """
    remote = job.remote_policy
    if not remote or remote == "unknown":
        remote = oc.remote_policy
    if job.salary_min is not None or job.salary_max is not None:
        smin, smax, scur = job.salary_min, job.salary_max, job.salary_currency
    else:
        smin, smax, scur = oc.salary_min, oc.salary_max, oc.salary_currency
    return MergedValues(oc.skills, remote, smin, smax, scur)


@dataclass
class _JobOutcome:
    job_id: str
    ok: bool
    skills: list[str] = field(default_factory=list)
    remote_policy: str = "unknown"
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


def _extract_many(
    extractor: DeepSeekExtractor, jobs: list[Job], workers: int
) -> list[_JobOutcome]:
    """Call the LLM concurrently for a set of jobs (2 retries each)."""

    def one(job: Job) -> _JobOutcome:
        rec = _job_to_record(job)
        last_err = None
        for _ in range(3):
            try:
                res, pin, pout = extractor.extract_with_usage(rec)
                return _JobOutcome(
                    job.id, True, res.skills, res.remote_policy, res.salary_min,
                    res.salary_max, res.salary_currency, pin, pout,
                )
            except Exception as exc:  # noqa: BLE001 - retry then record
                last_err = f"{type(exc).__name__}: {exc}"
        return _JobOutcome(job.id, False, error=last_err)

    outcomes: list[_JobOutcome] = []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for oc in pool.map(one, jobs):
            outcomes.append(oc)
    return outcomes


# --- Sample comparison (no DB writes) ----------------------------------------
@dataclass
class SampleReport:
    n: int = 0
    ok: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # aggregate diffs
    heur_skill_avg: float = 0.0
    llm_skill_avg: float = 0.0
    remote_changed: int = 0
    salary_added: int = 0
    salary_removed: int = 0
    llm_narrower: int = 0  # llm skills ⊊ heuristic (dropped spurious tags, incl. → [])
    llm_broader: int = 0   # llm added skills the heuristic missed
    llm_emptied: int = 0   # heuristic had skills, llm found none (false-positive removal)
    examples: list[dict] = field(default_factory=list)

    @property
    def cost(self) -> float:
        return cost_cny(self.prompt_tokens, self.completion_tokens)

    def extrapolate(self, total_jobs: int) -> float:
        if self.ok == 0:
            return 0.0
        return self.cost / self.ok * total_jobs


def run_sample_comparison(n: int = 100, workers: int = 8) -> SampleReport:
    ensure_schema()
    extractor = make_deepseek_extractor()
    rep = SampleReport()
    with session_scope() as s:
        jobs = list(
            s.execute(select(Job).order_by(func.random()).limit(n)).scalars()
        )
        rep.n = len(jobs)
        by_id = {j.id: j for j in jobs}
        outcomes = _extract_many(extractor, jobs, workers)

        heur_total = llm_total = 0
        for oc in outcomes:
            job = by_id[oc.job_id]
            rep.prompt_tokens += oc.prompt_tokens
            rep.completion_tokens += oc.completion_tokens
            if not oc.ok:
                rep.failed += 1
                continue
            rep.ok += 1
            merged = merge_extraction(job, oc)  # what we'd actually write
            h_sk = set(job.skills or [])
            l_sk = set(merged.skills or [])
            heur_total += len(h_sk)
            llm_total += len(l_sk)
            if job.remote_policy != merged.remote_policy:
                rep.remote_changed += 1  # only gap-fills (was 'unknown'), never overrides
            h_sal = job.salary_max is not None
            m_sal = merged.salary_max is not None
            if m_sal and not h_sal:
                rep.salary_added += 1
            if h_sal and not m_sal:
                rep.salary_removed += 1  # should be 0 under the merge policy
            if l_sk < h_sk:  # proper subset — includes the l_sk == set() case
                rep.llm_narrower += 1
            if l_sk - h_sk:
                rep.llm_broader += 1
            if h_sk and not l_sk:
                rep.llm_emptied += 1
            if len(rep.examples) < 12 and (h_sk != l_sk or job.remote_policy != merged.remote_policy):
                rep.examples.append({
                    "title": job.title[:48],
                    "company": job.company_id,
                    "heur_skills": sorted(h_sk),
                    "llm_skills": sorted(l_sk),
                    "heur_remote": job.remote_policy,
                    "llm_remote": merged.remote_policy,
                })
        rep.heur_skill_avg = heur_total / rep.ok if rep.ok else 0
        rep.llm_skill_avg = llm_total / rep.ok if rep.ok else 0
    return rep


# --- Full rebuild (writes, resumable, cost-capped) ---------------------------
@dataclass
class RebuildStats:
    total_target: int = 0
    processed: int = 0
    updated: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    halted: bool = False
    halt_reason: str | None = None

    @property
    def cost(self) -> float:
        return cost_cny(self.prompt_tokens, self.completion_tokens)


def _copy_fallback(job: Job) -> None:
    """Preserve the current (heuristic) values for comparison / rollback — once."""
    if job.extraction_source != TARGET_SOURCE and not job.skills_fallback:
        job.skills_fallback = list(job.skills or [])
        job.remote_policy_fallback = job.remote_policy
        job.salary_min_fallback = job.salary_min
        job.salary_max_fallback = job.salary_max
        job.salary_currency_fallback = job.salary_currency


def rebuild_extraction(
    batch_size: int = 50,
    workers: int = 8,
    limit: int | None = None,
    ceiling_cny: float | None = None,
    on_batch=None,
) -> RebuildStats:
    ensure_schema()
    extractor = make_deepseek_extractor()
    ceiling = config.EXTRACTION_COST_CEILING_CNY if ceiling_cny is None else ceiling_cny
    stats = RebuildStats()

    with session_scope() as s:
        stats.total_target = s.scalar(
            select(func.count()).select_from(Job).where(Job.extraction_source != TARGET_SOURCE)
        ) or 0

    remaining = stats.total_target if limit is None else min(limit, stats.total_target)

    while remaining > 0:
        take = min(batch_size, remaining)
        with session_scope() as s:
            jobs = list(
                s.execute(
                    select(Job)
                    .where(Job.extraction_source != TARGET_SOURCE)
                    .order_by(Job.id)
                    .limit(take)
                ).scalars()
            )
            if not jobs:
                break
            outcomes = {oc.job_id: oc for oc in _extract_many(extractor, jobs, workers)}
            for job in jobs:
                oc = outcomes[job.id]
                stats.processed += 1
                stats.prompt_tokens += oc.prompt_tokens
                stats.completion_tokens += oc.completion_tokens
                if not oc.ok:
                    stats.failed += 1
                    continue  # leave heuristic in place; a re-run will retry
                merged = merge_extraction(job, oc)
                _copy_fallback(job)
                job.skills = merged.skills
                job.remote_policy = merged.remote_policy
                job.salary_min = merged.salary_min
                job.salary_max = merged.salary_max
                job.salary_currency = merged.salary_currency
                job.salary_inferred = False
                job.extraction_source = TARGET_SOURCE
                stats.updated += 1
            # batch is committed on exiting session_scope (resumable checkpoint)

        remaining -= len(jobs)
        if on_batch:
            on_batch(stats)

        # HARD STOP: never spend beyond the ceiling without asking.
        if stats.cost >= ceiling:
            stats.halted = True
            stats.halt_reason = (
                f"cost ¥{stats.cost:.2f} reached ceiling ¥{ceiling:.2f}"
            )
            break

    return stats


@dataclass
class _RFOutcome:
    job_id: str
    ok: bool
    role_family: str = "other"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


def _classify_many(
    extractor: DeepSeekExtractor, jobs: list[Job], workers: int
) -> list[_RFOutcome]:
    def one(job: Job) -> _RFOutcome:
        rec = _job_to_record(job)
        last_err = None
        for _ in range(3):
            try:
                label, pin, pout = extractor.classify_role_family_with_usage(rec)
                return _RFOutcome(job.id, True, label, pin, pout)
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
        return _RFOutcome(job.id, False, error=last_err)

    outcomes: list[_RFOutcome] = []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for oc in pool.map(one, jobs):
            outcomes.append(oc)
    return outcomes


def rebuild_role_family(
    batch_size: int = 100,
    workers: int = 12,
    limit: int | None = None,
    ceiling_cny: float | None = None,
    on_batch=None,
) -> RebuildStats:
    """Classify each job's role_family via DeepSeek. Resumable (role_family IS NULL) and
    cost-capped (hard stop at the ¥ ceiling), mirroring rebuild_extraction."""
    ensure_schema()
    extractor = make_deepseek_extractor()
    ceiling = config.EXTRACTION_COST_CEILING_CNY if ceiling_cny is None else ceiling_cny
    stats = RebuildStats()

    with session_scope() as s:
        stats.total_target = s.scalar(
            select(func.count()).select_from(Job).where(Job.role_family.is_(None))
        ) or 0

    remaining = stats.total_target if limit is None else min(limit, stats.total_target)

    while remaining > 0:
        take = min(batch_size, remaining)
        with session_scope() as s:
            jobs = list(
                s.execute(
                    select(Job).where(Job.role_family.is_(None)).order_by(Job.id).limit(take)
                ).scalars()
            )
            if not jobs:
                break
            outcomes = {oc.job_id: oc for oc in _classify_many(extractor, jobs, workers)}
            for job in jobs:
                oc = outcomes[job.id]
                stats.processed += 1
                stats.prompt_tokens += oc.prompt_tokens
                stats.completion_tokens += oc.completion_tokens
                if not oc.ok:
                    stats.failed += 1
                    continue  # leave NULL; a re-run retries it
                job.role_family = oc.role_family
                stats.updated += 1

        remaining -= len(jobs)
        if on_batch:
            on_batch(stats)

        if stats.cost >= ceiling:
            stats.halted = True
            stats.halt_reason = f"cost ¥{stats.cost:.2f} reached ceiling ¥{ceiling:.2f}"
            break

    return stats


def rollback_extraction() -> int:
    """Restore heuristic values from the *_fallback columns. Returns rows restored."""
    ensure_schema()
    restored = 0
    with session_scope() as s:
        for job in s.execute(
            select(Job).where(Job.extraction_source == TARGET_SOURCE)
        ).scalars():
            job.skills = list(job.skills_fallback or [])
            job.remote_policy = job.remote_policy_fallback
            job.salary_min = job.salary_min_fallback
            job.salary_max = job.salary_max_fallback
            job.salary_currency = job.salary_currency_fallback
            job.extraction_source = "heuristic"
            restored += 1
    return restored
