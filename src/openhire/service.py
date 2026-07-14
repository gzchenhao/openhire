"""Service layer — the pure logic behind the five MCP tools.

Kept transport-agnostic (plain functions over a SQLAlchemy Session) so it is unit-tested
directly and reused by both the MCP server and the CLI. The MCP tool wrappers in
mcp_server.py are thin.

Protocol contracts (README §MCP 工具契约):
  search_jobs      → JobPosting[] (hard filter + fixed ranking only; each has the 5 fields)
  get_company_info → aggregate trust signals only, never individual candidate data
  watch_intent     → { watch_id, status } from anonymous fingerprint + filters (no PII)
  check_watches    → new matches since last notification (client-pull; stdio has no push)
  apply            → { delivered_via, receipt_id, resume_transmitted: false } — refuses résumés
"""

from __future__ import annotations

import datetime as dt
import secrets
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import Application, Company, Job, Watch
from .errors import OpenHireError
from .pipeline.ranking import freshness, match_quality, rank_score

DELIVERED_VIA = "employer_site"  # v0.1 always the employer's own channel

# --- remote scope classification (protocol truthfulness) ----------------------
# "remote" alone hides whether a role is open worldwide or geo-fenced. We classify the
# ATS location text into a coarse, honest bucket + surface the matched regions. Heuristic
# and best-effort (v0.1): unqualified remote → worldwide; a named macro-region →
# region_locked; a named single country → country_locked.
_REGION_TOKENS = {
    "emea": "EMEA", "apac": "APAC", "americas": "Americas", "latam": "LATAM",
    "europe": "Europe", "north america": "North America", "asia": "Asia",
    "eu": "EU", "ap": "APAC",
}
_COUNTRY_TOKENS = {
    "united states": "US", "usa": "US", "u.s.": "US", "us-": "US", "us ": "US",
    "united kingdom": "UK", "uk": "UK", "canada": "Canada", "germany": "Germany",
    "india": "India", "france": "France", "ireland": "Ireland", "australia": "Australia",
    "spain": "Spain", "poland": "Poland", "netherlands": "Netherlands", "brazil": "Brazil",
    "singapore": "Singapore", "japan": "Japan", "israel": "Israel", "mexico": "Mexico",
}
_WORLDWIDE_TOKENS = ("worldwide", "global", "anywhere", "any location")


def classify_remote(remote_policy: str | None, location: str | None) -> tuple[str | None, list[str]]:
    """Return (remote_scope, eligible_regions) for a posting. Non-remote → (None, [])."""
    if remote_policy != "remote":
        return None, []
    loc = (location or "").lower()
    if not loc or any(t in loc for t in _WORLDWIDE_TOKENS) or loc.strip() in ("remote", "fully remote"):
        return "worldwide", []
    regions = sorted({label for tok, label in _REGION_TOKENS.items() if tok in loc})
    if regions:
        return "region_locked", regions
    countries = sorted({label for tok, label in _COUNTRY_TOKENS.items() if tok in loc})
    if countries:
        return "country_locked", countries
    # Remote but with an unrecognized qualifier — treat as worldwide, no asserted regions.
    return "worldwide", []

# Keys / markers that would indicate someone is trying to push a résumé/PII through.
_RESUME_KEYS = {
    "resume", "cv", "resume_text", "resume_content", "file", "attachment",
    "document", "cover_letter", "profile", "pii", "email", "phone", "name",
    "first_name", "last_name", "linkedin", "portfolio",
}
_MAX_ID_LEN = 200  # a real job_id/fingerprint is short; long text ⇒ crammed content


def _now(now: dt.datetime | None) -> dt.datetime:
    return now or dt.datetime.now(dt.timezone.utc)


def _aware(d: dt.datetime | None) -> dt.datetime | None:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


# --- serialization ------------------------------------------------------------
def job_posting(job: Job, company: Company | None, requested_skills: list[str], now: dt.datetime) -> dict:
    """schema.org/JobPosting + the five OpenHire fields (protocol contract)."""
    mq = match_quality(requested_skills, job.skills)
    fr = freshness(job.verified_at, now)
    # datePosted is the employer's REAL posting date (ATS), not our crawl date; fall back
    # to first_seen_at only when the ATS exposed no date. days_open = age of the posting.
    posted = _aware(job.posted_at) or _aware(job.first_seen_at)
    _rs, _regions = classify_remote(job.remote_policy, job.location)
    return {
        "@type": "JobPosting",
        "job_id": job.id,
        "title": job.title,
        "company": company.name if company else job.company_id,
        "company_id": job.company_id,
        "datePosted": posted.date().isoformat() if posted else None,
        "days_open": (now.date() - posted.date()).days if posted else None,
        "location": job.location,
        "remote_policy": job.remote_policy,
        "remote_scope": _rs,          # worldwide | region_locked | country_locked | null
        "eligible_regions": _regions,  # matched regions/countries ([] = worldwide/unknown)
        "role_family": getattr(job, "role_family", None),  # null until the DeepSeek pass runs
        "skills": list(job.skills or []),
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "salary_inferred": job.salary_inferred,
        # ---- the five OpenHire protocol fields ----
        "verified_at": _aware(job.verified_at).isoformat() if job.verified_at else None,  # ①
        "source": job.source,                                                             # ②
        "ghost_score": round(job.ghost_score, 4) if job.ghost_score is not None else None,  # ③
        "response_sla_days": job.response_sla_days,                                        # ④
        "apply_channel": job.apply_channel,                                               # ⑤
        # ---- ranking transparency (client may re-rank; server sort is fixed) ----
        "match_quality": round(mq, 4),
        "freshness": round(fr, 4),
        "rank_score": round(rank_score(mq, fr), 6),
    }


# --- hard filter + fixed ranking ---------------------------------------------
def _filter_and_rank(
    session: Session,
    skills: list[str] | None,
    remote: bool | None,
    min_salary: int | None,
    since: dt.datetime | None,
    limit: int,
    now: dt.datetime,
    required_skills: list[str] | None = None,
    currency: str | None = None,
    require_stated_salary: bool = False,
    remote_scope: str | None = None,
    role_family: str | None = None,
) -> list[tuple[Job, float]]:
    """Server-side HARD FILTER (skills ∩/∀, remote, salary, freshness window) + FIXED sort.
    Precise re-ranking is intentionally left to the client agent."""
    stmt = select(Job).where(Job.delisted_at.is_(None))

    if remote is True:
        stmt = stmt.where(Job.remote_policy == "remote")
    if min_salary is not None:
        # Keep jobs whose stated pay could meet the floor. Unstated pay is KEPT here (it
        # cannot be ruled out) unless require_stated_salary asks to exclude it.
        stmt = stmt.where(
            (Job.salary_max.isnot(None) & (Job.salary_max >= min_salary))
            | (Job.salary_min.isnot(None) & (Job.salary_min >= min_salary))
            | (Job.salary_min.is_(None) & Job.salary_max.is_(None))
        )
    if require_stated_salary:
        stmt = stmt.where(Job.salary_min.isnot(None) | Job.salary_max.isnot(None))
    if currency:
        # A currency filter is meaningful only for stated pay → excludes unstated.
        stmt = stmt.where(Job.salary_currency == currency.upper())
    if since is not None:
        stmt = stmt.where(Job.first_seen_at > since)

    requested = [s.lower() for s in (skills or [])]
    req_set = set(requested)
    all_required = {s.lower() for s in (required_skills or [])}
    rf = (role_family or "").lower() or None

    scored: list[tuple[Job, float]] = []
    for job in session.execute(stmt).scalars():
        job_skills = {s.lower() for s in (job.skills or [])}
        if req_set and not (req_set & job_skills):
            continue  # ANY-overlap (skills 交集)
        if all_required and not all_required.issubset(job_skills):
            continue  # AND — every required skill must be present
        if remote_scope:
            scope, _ = classify_remote(job.remote_policy, job.location)
            if scope != remote_scope:
                continue
        if rf and (getattr(job, "role_family", None) or "").lower() != rf:
            continue
        mq = match_quality(requested or list(all_required), job.skills)
        fr = freshness(job.verified_at, now)
        scored.append((job, rank_score(mq, fr)))

    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:limit]


def search_jobs(
    session: Session,
    skills: list[str] | None = None,
    remote: bool | None = None,
    min_salary: int | None = None,
    limit: int = 20,
    now: dt.datetime | None = None,
    required_skills: list[str] | None = None,
    currency: str | None = None,
    require_stated_salary: bool = False,
    remote_scope: str | None = None,
    role_family: str | None = None,
) -> list[dict]:
    now = _now(now)
    limit = max(1, min(int(limit), 100))
    ranked = _filter_and_rank(
        session, skills, remote, min_salary, None, limit, now,
        required_skills=required_skills, currency=currency,
        require_stated_salary=require_stated_salary, remote_scope=remote_scope,
        role_family=role_family,
    )
    company_ids = {j.company_id for j, _ in ranked}
    companies = {
        c.id: c
        for c in session.execute(select(Company).where(Company.id.in_(company_ids))).scalars()
    } if company_ids else {}
    return [job_posting(j, companies.get(j.company_id), skills or [], now) for j, _ in ranked]


# --- company trust signals (aggregate only) ----------------------------------
def get_company_info(session: Session, company_id: str, now: dt.datetime | None = None) -> dict:
    company = session.get(Company, company_id)
    if company is None:
        raise OpenHireError("ERR_COMPANY_NOT_FOUND", f"No company with id '{company_id}'.")

    live = select(Job).where(Job.company_id == company_id, Job.delisted_at.is_(None))
    active_jobs = session.scalar(
        select(func.count()).select_from(live.subquery())
    ) or 0
    ghost_avg = session.scalar(
        select(func.avg(Job.ghost_score)).where(
            Job.company_id == company_id, Job.delisted_at.is_(None)
        )
    )
    # Aggregate, anonymous signals ONLY — never any individual candidate data.
    # NOTE: `verified` was removed (it was always false in v0.1 — a false trust signal).
    # `index_built_at` is when this index was last built (a batch timestamp shared across
    # companies), honestly named rather than implying a per-company crawl time.
    return {
        "company_id": company.id,
        "company": company.name,
        "ghost_score_avg": round(ghost_avg, 4) if ghost_avg is not None else None,
        "active_jobs": int(active_jobs),
        "index_built_at": _aware(company.last_crawled_at).isoformat()
        if company.last_crawled_at else None,
    }


# --- watches ------------------------------------------------------------------
def _new_id(session: Session, model, pk_attr: str, prefix: str) -> str:
    for _ in range(20):
        candidate = f"{prefix}{secrets.token_hex(2)}"  # e.g. w_8a3f
        if session.get(model, candidate) is None:
            return candidate
    return f"{prefix}{secrets.token_hex(4)}"


def _clean_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Keep only the whitelisted, non-PII filter keys."""
    allowed = {}
    if filters.get("skills"):
        allowed["skills"] = [str(s).lower() for s in filters["skills"]]
    if filters.get("required_skills"):
        allowed["required_skills"] = [str(s).lower() for s in filters["required_skills"]]
    if filters.get("remote") is not None:
        allowed["remote"] = bool(filters["remote"])
    if filters.get("role_family"):
        allowed["role_family"] = str(filters["role_family"]).lower()
    if filters.get("min_salary") is not None:
        allowed["min_salary"] = int(filters["min_salary"])
    # Reject any stray PII keys defensively (red line #1).
    leaked = set(filters) & _RESUME_KEYS
    if leaked:
        raise OpenHireError(
            "ERR_PII_NOT_ACCEPTED",
            f"Filters may not contain personal data ({', '.join(sorted(leaked))}). "
            "Only anonymous skills/remote/min_salary are stored.",
        )
    return allowed


def watch_intent(
    session: Session,
    fingerprint: str,
    filters: dict[str, Any],
    now: dt.datetime | None = None,
) -> dict:
    now = _now(now)
    _assert_anonymous(fingerprint)
    clean = _clean_filters(filters or {})
    watch_id = _new_id(session, Watch, "watch_id", "w_")
    session.add(
        Watch(
            watch_id=watch_id,
            fingerprint=fingerprint,
            filters=clean,
            created_at=now,
            active=True,
        )
    )
    # The fingerprint is client-owned and client-generated: the server stores it but can
    # NEVER regenerate or recover it. check_watches requires the SAME fingerprint, so the
    # client must persist it. (Red line #1: only this anonymous token is ever stored.)
    return {
        "watch_id": watch_id,
        "status": "active",
        "fingerprint": fingerprint,
        "fingerprint_notice": (
            "Persist this fingerprint yourself — the server cannot recover it. "
            "check_watches needs the identical fingerprint to return your matches."
        ),
    }


def check_watches(session: Session, fingerprint: str, now: dt.datetime | None = None) -> dict:
    now = _now(now)
    _assert_anonymous(fingerprint)
    watches = list(
        session.execute(
            select(Watch).where(Watch.fingerprint == fingerprint, Watch.active.is_(True))
        ).scalars()
    )
    results = []
    total_new = 0
    for w in watches:
        # Never notified → return the current baseline (all matches). Thereafter →
        # only jobs first seen strictly after the last notification (the increment).
        since = _aware(w.last_notified_at)
        f = w.filters or {}
        ranked = _filter_and_rank(
            session, f.get("skills"), f.get("remote"), f.get("min_salary"), since, 20, now,
            required_skills=f.get("required_skills"), role_family=f.get("role_family"),
        )
        company_ids = {j.company_id for j, _ in ranked}
        companies = {
            c.id: c
            for c in session.execute(
                select(Company).where(Company.id.in_(company_ids))
            ).scalars()
        } if company_ids else {}
        matches = [
            job_posting(j, companies.get(j.company_id), f.get("skills") or [], now)
            for j, _ in ranked
        ]
        total_new += len(matches)
        results.append(
            {
                "watch_id": w.watch_id,
                "since": since.isoformat() if since else None,
                "new_matches": matches,
            }
        )
        w.last_notified_at = now
    return {"fingerprint": fingerprint, "watches": len(watches), "new_matches": total_new, "results": results}


# --- apply (refuses résumés) --------------------------------------------------
def assert_no_resume(arguments: dict[str, Any]) -> None:
    """Raise if a caller tries to push a résumé/PII/file through apply (red line #1)."""
    leaked = {k for k in arguments if k.lower() in _RESUME_KEYS}
    if leaked:
        raise OpenHireError(
            "ERR_RESUME_NEVER_TRANSMITTED",
            "A résumé never transits the server. Remove "
            f"{', '.join(sorted(leaked))}; apply only takes an anonymous fingerprint. "
            "Open apply_channel to submit as yourself.",
        )


def _assert_anonymous(value: str) -> None:
    """Fingerprint/ids must be short anonymous tokens, not crammed résumé/PII text."""
    if value is None or len(str(value)) > _MAX_ID_LEN or "\n" in str(value):
        raise OpenHireError(
            "ERR_RESUME_NEVER_TRANSMITTED",
            "This looks like résumé/PII content, which never transits the server. "
            "Pass only a short anonymous fingerprint.",
        )


def apply(
    session: Session,
    job_id: str,
    fingerprint: str,
    authorized: bool,
    now: dt.datetime | None = None,
    extra_arguments: dict[str, Any] | None = None,
) -> dict:
    now = _now(now)
    # Red line #1 — never accept a résumé/file, no matter how it's smuggled in.
    assert_no_resume(extra_arguments or {})
    _assert_anonymous(fingerprint)
    _assert_anonymous(job_id)

    if authorized is not True:
        raise OpenHireError(
            "ERR_NOT_AUTHORIZED",
            "apply requires explicit per-job authorization (authorized=true).",
        )

    job = session.get(Job, job_id)
    if job is None:
        raise OpenHireError("ERR_JOB_NOT_FOUND", f"No job with id '{job_id}'.")

    receipt_id = _new_id(session, Application, "receipt_id", "r_")
    session.add(
        Application(
            receipt_id=receipt_id,
            job_id=job.id,
            fingerprint=fingerprint,
            authorized=True,
            delivered_via=DELIVERED_VIA,
            created_at=now,
        )
    )
    return {
        "delivered_via": DELIVERED_VIA,
        "receipt_id": receipt_id,
        "resume_transmitted": False,
        "apply_channel": job.apply_channel,
        "message": "Résumé never transited the server. Open apply_channel to apply as yourself.",
    }
