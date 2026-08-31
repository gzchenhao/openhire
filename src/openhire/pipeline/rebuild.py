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
import re
import time
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..ats.base import JobRecord
from ..db import Job, session_scope
from ..db.migrate import ensure_schema
from .extract import (
    LLM_SOURCES,
    DeepSeekExtractor,
    RateLimited,
    canonicalize_skills,
    classify_role_family_heuristic,
    make_deepseek_extractor,
    make_llm_extractor,
)

TARGET_SOURCE = "deepseek"

# Back off on 429 instead of hammering; give up on a job after this many rate-limited
# attempts, and stop the whole run after MAX_CONSECUTIVE_429 jobs die that way in a row
# (that means the plan's quota is gone, not that one call was unlucky).
_429_BACKOFF_SECONDS = (2.0, 5.0, 12.0, 30.0)
MAX_CONSECUTIVE_429 = 5


def cost_cny(prompt_tokens: int, completion_tokens: int, backend: str = "deepseek") -> float:
    """Cash cost in CNY. GLM runs inside a prepaid coding plan, so its rate is 0."""
    if backend == "glm":
        pin, pout = config.GLM_PRICE_INPUT_CNY, config.GLM_PRICE_OUTPUT_CNY
    else:
        pin, pout = config.DEEPSEEK_PRICE_INPUT_CNY, config.DEEPSEEK_PRICE_OUTPUT_CNY
    return prompt_tokens / 1_000_000 * pin + completion_tokens / 1_000_000 * pout


def _make_extractor(backend: str = "deepseek", model: str | None = None):
    """`deepseek` still goes through the module-level factory (tests patch it)."""
    if (backend or "deepseek") == "deepseek":
        return make_deepseek_extractor()
    return make_llm_extractor(backend, model)


def _source_label(extractor, backend: str = "deepseek") -> str:
    """Provenance stamp. Never let one LLM masquerade as another."""
    return getattr(extractor, "name", None) or (backend or TARGET_SOURCE)


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
    rate_limited: bool = False


def _retry_call(fn, attempts: int = 3):
    """Run `fn`, retrying failures. A 429 sleeps an escalating backoff first and gets its
    own extra attempts, because it means "come back later", not "this input is bad".

    Returns (value, error, rate_limited).
    """
    last_err = None
    hit_429 = 0
    tries = 0
    while tries < attempts:
        try:
            return fn(), None, False
        except RateLimited as exc:
            last_err = f"RateLimited: {exc}"
            if hit_429 >= len(_429_BACKOFF_SECONDS):
                return None, last_err, True
            time.sleep(_429_BACKOFF_SECONDS[hit_429])
            hit_429 += 1
        except Exception as exc:  # noqa: BLE001 - retry then record
            last_err = f"{type(exc).__name__}: {exc}"
            tries += 1
    return None, last_err, False


def _extract_many(
    extractor: DeepSeekExtractor, jobs: list[Job], workers: int
) -> list[_JobOutcome]:
    """Call the LLM concurrently for a set of jobs (2 retries each, 429s backed off)."""

    def one(job: Job) -> _JobOutcome:
        rec = _job_to_record(job)
        value, err, limited = _retry_call(lambda: extractor.extract_with_usage(rec))
        if value is None:
            return _JobOutcome(job.id, False, error=err, rate_limited=limited)
        res, pin, pout = value
        return _JobOutcome(
            job.id, True, res.skills, res.remote_policy, res.salary_min,
            res.salary_max, res.salary_currency, pin, pout,
        )

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


# --- Backend bake-off (no DB writes) -----------------------------------------
# Model selection is decided on measured output, not on vibes. The DB already holds
# DeepSeek's skills for 16k jobs, so the incumbent is free to compare against: we only
# pay (in plan tokens) for the challengers.

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def is_chinese_jd(text: str) -> bool:
    """A JD counts as Chinese when CJK characters are a real share of it, not a stray
    company name in an English posting."""
    if not text:
        return False
    sample = text[:2000]
    return len(_CJK_RE.findall(sample)) >= 20


@dataclass
class BackendResult:
    backend: str
    model: str
    ok: int = 0
    failed: int = 0
    seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    skill_total: int = 0
    # vs the stored DeepSeek extraction, on the same jobs
    same: int = 0        # identical skill sets
    superset: int = 0    # found everything DeepSeek did, plus more
    subset: int = 0      # strictly fewer (dropped tags DeepSeek had)
    overlap: int = 0     # partial - each found something the other missed
    emptied: int = 0     # DeepSeek had skills, this backend found none
    jaccard_total: float = 0.0
    # Chinese-JD slice only
    cn_ok: int = 0
    cn_skill_total: int = 0
    cn_ds_skill_total: int = 0
    cn_jaccard_total: float = 0.0
    cn_emptied: int = 0
    per_job: dict = field(default_factory=dict)

    @property
    def avg_skills(self) -> float:
        return self.skill_total / self.ok if self.ok else 0.0

    @property
    def avg_jaccard(self) -> float:
        return self.jaccard_total / self.ok if self.ok else 0.0

    @property
    def cn_avg_skills(self) -> float:
        return self.cn_skill_total / self.cn_ok if self.cn_ok else 0.0

    @property
    def cn_avg_jaccard(self) -> float:
        return self.cn_jaccard_total / self.cn_ok if self.cn_ok else 0.0

    @property
    def secs_per_job(self) -> float:
        return self.seconds / self.ok if self.ok else 0.0


@dataclass
class BakeOff:
    n: int = 0
    cn: int = 0
    ds_skill_total: int = 0
    ds_cn_skill_total: int = 0
    results: list[BackendResult] = field(default_factory=list)
    jobs: list[dict] = field(default_factory=list)

    @property
    def ds_avg_skills(self) -> float:
        return self.ds_skill_total / self.n if self.n else 0.0

    @property
    def ds_cn_avg_skills(self) -> float:
        return self.ds_cn_skill_total / self.cn if self.cn else 0.0


def _sample_jobs(s: Session, n: int, cn_min: int) -> list[Job]:
    """N jobs already extracted by DeepSeek, forcing at least `cn_min` Chinese JDs so the
    Chinese-language quality bar is actually measured and not left to a random draw."""
    pool = list(
        s.execute(
            select(Job)
            .where(Job.extraction_source == "deepseek")
            .order_by(func.random())
            .limit(n * 12)
        ).scalars()
    )
    cn = [j for j in pool if is_chinese_jd(j.description_raw or "")]
    en = [j for j in pool if j not in cn]
    picked = cn[:cn_min] + en[: max(0, n - min(len(cn), cn_min))]
    return picked[:n]


def run_backend_comparison(
    n: int = 100,
    cn_min: int = 30,
    backends: tuple[tuple[str, str], ...] = (
        ("glm", "glm-5.3-flash"),
        ("glm", "glm-5.3"),
    ),
    workers: int = 4,
) -> BakeOff:
    """Run each candidate backend over the SAME jobs and diff against stored DeepSeek."""
    ensure_schema()
    rep = BakeOff()
    with session_scope() as s:
        jobs = _sample_jobs(s, n, cn_min)
        rep.n = len(jobs)
        stored = {
            j.id: (
                set(j.skills or []),
                is_chinese_jd(j.description_raw or ""),
                j.title,
                j.company_id,
            )
            for j in jobs
        }
        rep.cn = sum(1 for v in stored.values() if v[1])
        rep.ds_skill_total = sum(len(v[0]) for v in stored.values())
        rep.ds_cn_skill_total = sum(len(v[0]) for v in stored.values() if v[1])

        for backend, model in backends:
            extractor = make_llm_extractor(backend, model)
            res = BackendResult(backend=_source_label(extractor, backend), model=model)
            t0 = time.monotonic()
            outcomes = _extract_many(extractor, jobs, workers)
            res.seconds = time.monotonic() - t0
            for oc in outcomes:
                res.prompt_tokens += oc.prompt_tokens
                res.completion_tokens += oc.completion_tokens
                if not oc.ok:
                    res.failed += 1
                    continue
                res.ok += 1
                ds, is_cn, _title, _co = stored[oc.job_id]
                got = set(canonicalize_skills(oc.skills))
                res.per_job[oc.job_id] = sorted(got)
                res.skill_total += len(got)
                union = ds | got
                jac = len(ds & got) / len(union) if union else 1.0
                res.jaccard_total += jac
                if got == ds:
                    res.same += 1
                elif ds and not got:
                    res.emptied += 1
                    res.subset += 1
                elif got > ds:
                    res.superset += 1
                elif got < ds:
                    res.subset += 1
                else:
                    res.overlap += 1
                if is_cn:
                    res.cn_ok += 1
                    res.cn_skill_total += len(got)
                    res.cn_ds_skill_total += len(ds)
                    res.cn_jaccard_total += jac
                    if ds and not got:
                        res.cn_emptied += 1
            rep.results.append(res)

        for jid, (ds, is_cn, title, co) in stored.items():
            rep.jobs.append({
                "id": jid, "company": co, "title": title, "cn": is_cn,
                "deepseek": sorted(ds),
                **{r.model: r.per_job.get(jid) for r in rep.results},
            })
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
    backend: str = TARGET_SOURCE
    rate_limited: int = 0

    @property
    def cost(self) -> float:
        return cost_cny(self.prompt_tokens, self.completion_tokens, self.backend)


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
    backend: str = TARGET_SOURCE,
    model: str | None = None,
) -> RebuildStats:
    """Re-extract every job NOT already done by an LLM backend.

    The target set is `extraction_source NOT IN LLM_SOURCES` rather than `!= <this
    backend>`: with two LLM backends in play, the old test would have made glm and
    deepseek endlessly re-extract each other's rows for no quality gain.
    """
    ensure_schema()
    extractor = _make_extractor(backend, model)
    source = _source_label(extractor, backend)
    ceiling = config.EXTRACTION_COST_CEILING_CNY if ceiling_cny is None else ceiling_cny
    stats = RebuildStats(backend=source)
    consecutive_429 = 0

    with session_scope() as s:
        stats.total_target = s.scalar(
            select(func.count()).select_from(Job)
            .where(Job.extraction_source.notin_(LLM_SOURCES))
        ) or 0

    remaining = stats.total_target if limit is None else min(limit, stats.total_target)

    while remaining > 0:
        take = min(batch_size, remaining)
        with session_scope() as s:
            jobs = list(
                s.execute(
                    select(Job)
                    .where(Job.extraction_source.notin_(LLM_SOURCES))
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
                    if oc.rate_limited:
                        stats.rate_limited += 1
                        consecutive_429 += 1
                    else:
                        consecutive_429 = 0
                    continue  # leave heuristic in place; a re-run will retry
                consecutive_429 = 0
                merged = merge_extraction(job, oc)
                _copy_fallback(job)
                job.skills = merged.skills
                job.remote_policy = merged.remote_policy
                job.salary_min = merged.salary_min
                job.salary_max = merged.salary_max
                job.salary_currency = merged.salary_currency
                job.salary_inferred = False
                job.extraction_source = source
                stats.updated += 1
            # batch is committed on exiting session_scope (resumable checkpoint)

        remaining -= len(jobs)
        if on_batch:
            on_batch(stats)

        # HARD STOP: repeated 429s mean the plan quota is gone, not that one call was
        # unlucky. Progress is already committed, so a re-run resumes from here.
        if consecutive_429 >= MAX_CONSECUTIVE_429:
            stats.halted = True
            stats.halt_reason = (
                f"{consecutive_429} consecutive rate-limited jobs (HTTP 429)"
            )
            break

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
    rate_limited: bool = False


def _classify_many(
    extractor: DeepSeekExtractor, jobs: list[Job], workers: int
) -> list[_RFOutcome]:
    def one(job: Job) -> _RFOutcome:
        rec = _job_to_record(job)
        value, err, limited = _retry_call(
            lambda: extractor.classify_role_family_with_usage(rec)
        )
        if value is None:
            return _RFOutcome(job.id, False, error=err, rate_limited=limited)
        label, pin, pout = value
        return _RFOutcome(job.id, True, label, pin, pout)

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
    backend: str = TARGET_SOURCE,
    model: str | None = None,
) -> RebuildStats:
    """Classify each job's role_family with an LLM. Resumable (role_family IS NULL) and
    cost-capped (hard stop at the CNY ceiling), mirroring rebuild_extraction."""
    ensure_schema()
    extractor = _make_extractor(backend, model)
    ceiling = config.EXTRACTION_COST_CEILING_CNY if ceiling_cny is None else ceiling_cny
    stats = RebuildStats(backend=_source_label(extractor, backend))
    consecutive_429 = 0

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
                    if oc.rate_limited:
                        stats.rate_limited += 1
                        consecutive_429 += 1
                    else:
                        consecutive_429 = 0
                    continue  # leave NULL; a re-run retries it
                consecutive_429 = 0
                job.role_family = oc.role_family
                stats.updated += 1

        remaining -= len(jobs)
        if on_batch:
            on_batch(stats)

        if consecutive_429 >= MAX_CONSECUTIVE_429:
            stats.halted = True
            stats.halt_reason = (
                f"{consecutive_429} consecutive rate-limited jobs (HTTP 429)"
            )
            break

        if stats.cost >= ceiling:
            stats.halted = True
            stats.halt_reason = f"cost ¥{stats.cost:.2f} reached ceiling ¥{ceiling:.2f}"
            break

    return stats


def backfill_role_family_heuristic(limit: int | None = None) -> tuple[int, int]:
    """Free, no-LLM pass: label `role_family IS NULL` rows by title keywords.

    Returns (labelled, still_null). Rows the classifier is unsure about are left NULL so
    the paid DeepSeek pass — which resumes on `role_family IS NULL` — can still claim them.
    """
    ensure_schema()
    labelled = still_null = 0
    with session_scope() as s:
        stmt = select(Job).where(Job.role_family.is_(None)).order_by(Job.id)
        if limit:
            stmt = stmt.limit(limit)
        for job in s.execute(stmt).scalars():
            family = classify_role_family_heuristic(job.title or "", job.description_raw or "")
            if family:
                job.role_family = family
                labelled += 1
            else:
                still_null += 1
    return labelled, still_null


def rollback_extraction() -> int:
    """Restore heuristic values from the *_fallback columns. Returns rows restored."""
    ensure_schema()
    restored = 0
    with session_scope() as s:
        for job in s.execute(
            select(Job).where(Job.extraction_source.in_(LLM_SOURCES))
        ).scalars():
            job.skills = list(job.skills_fallback or [])
            job.remote_policy = job.remote_policy_fallback
            job.salary_min = job.salary_min_fallback
            job.salary_max = job.salary_max_fallback
            job.salary_currency = job.salary_currency_fallback
            job.extraction_source = "heuristic"
            restored += 1
    return restored
