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
import difflib
import hashlib
import re
import secrets
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .db import Application, Company, Job, Watch
from .errors import OpenHireError
from .ats import apply_url_is_trusted
from .pipeline.ghost_score import ghost_reason
from .seed.claims import employer_correction
from .seed import not_indexed
from .pipeline.ranking import freshness, match_quality, rank_score

DELIVERED_VIA = "employer_site"  # v0.1 always the employer's own channel

# Most rows one call will return. Asking for more has always returned this many and said
# nothing about it, so a reviewer pulled `company=XPeng limit=200`, got 100 of 198, and
# concluded the index held 100 XPeng jobs. A later skill search then surfaced two XPeng
# roles that were "not in the full list" — which reads as a consistency bug and is really
# the same silent cut. `offset` reaches the rest; nothing told them to page. Public so the
# CLI and the MCP boundary can say when it bit, without changing search_jobs' return type.
MAX_PAGE_SIZE = 100

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
# Short codes are matched on word boundaries: a plain substring "us" fired on "Austin",
# "campus" and "business", and "Remote, U.S" (no trailing period) matched nothing at all
# and fell through to "worldwide", which told a reader in Guangzhou that a US-only role
# was open to them.
_COUNTRY_PATTERNS = (
    (re.compile(r"(?<![a-z])(united states|u\.s\.?a?\.?|usa|us)(?![a-z])"), "US"),
    (re.compile(r"(?<![a-z])(united kingdom|u\.k\.?|uk)(?![a-z])"), "UK"),
)
_COUNTRY_TOKENS = {
    "canada": "Canada", "germany": "Germany",
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
    countries = {label for tok, label in _COUNTRY_TOKENS.items() if tok in loc}
    countries |= {label for pat, label in _COUNTRY_PATTERNS if pat.search(loc)}
    if countries:
        return "country_locked", sorted(countries)
    # Remote with a qualifier we could not read ("Remote - Ann Arbor, MI"). Saying
    # "worldwide" here asserted something the text never said; say we do not know.
    return "unknown", []

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


# --- salary period normalisation ----------------------------------------------
# `--min-salary` is an annual floor. Chinese portals publish 月薪, so a 25K-50K 元/月 role
# is stored as 25000–50000 with salary_period='monthly'. Comparing that raw against an
# annual floor would silently drop every Chinese job, so comparisons annualise (×12).
# Storage is untouched: what the employer published is what we show.
MONTHS_PER_YEAR = 12


def _annualised(column):
    """SQL expression: the column's value expressed as an annual figure."""
    return case((Job.salary_period == "monthly", column * MONTHS_PER_YEAR), else_=column)


def annualise(value: int | None, period: str | None) -> int | None:
    """Python-side twin of `_annualised`, for callers comparing a single job."""
    if value is None:
        return None
    return value * MONTHS_PER_YEAR if period == "monthly" else value




# --- skill vocabulary ---------------------------------------------------------
# The LLM extractor emits free-form tags and nothing ever normalised them, so the same
# skill lives under several spellings: "autonomous driving" (54 rows) alongside
# "autonomous-driving" (81) and "autonomous_driving" (1). Measured 2026-09-20 over the
# live index: 1,263 groups differ ONLY by hyphen / space / underscore, covering 2,805
# distinct tags and 13,116 row-occurrences. Searching the commonest spelling of
# "autonomous driving" missed 40% of the rows that have it; "data analysis" missed 58%.
#
# A reviewer read that as "OpenHire has no autonomous-driving coverage at XPeng". The
# coverage was there; the query could not reach it.
#
# Matching therefore compares separator-insensitively. Storage keeps the employer's and
# the extractor's own spelling: this is a read-time equivalence, not a rewrite, so a real
# vocabulary pass later (report 028) can change the canonical form without a migration.
# Defined next to match_quality so the filter and the score can never drift apart.
from .pipeline.ranking import expand_skill, normalize_skill  # noqa: E402  (placed with its explanation)


# --- salary plausibility ------------------------------------------------------
# What the employer published is what we show, EXCEPT where the ATS published a number
# that cannot mean what its own period field says it means. Three shapes, all measured in
# the live index on 2026-09-20:
#
#   * `salary_min = 0` (90 live rows, e.g. Cloudflare 0–292,000 USD "annual"). Zero is the
#     ATS spelling of "not specified", and publishing it as a floor says the job pays from
#     nothing.
#   * An "annual" range that is plainly an hourly rate (Dexterity Materials Handler
#     22–27 USD "annual"). We were telling an agent the job pays $27 a year.
#   * A pair whose two halves are in different units (Fivetran BDR 15–103,259).
#
# In every case the honest output is the one we already use for `updated_at`: say we do not
# know, rather than publish a number we cannot stand behind. Storage is untouched; this is
# a read-time judgement, so a re-crawl or a better parser can change it without a migration.
ANNUAL_FLOOR = 5000     # below this an "annual" figure is an hourly/daily rate
MONTHLY_FLOOR = 500     # same idea for monthly-quoted pay (Chinese portals)
MAX_RANGE_RATIO = 200   # min and max this far apart are not the same unit


def usable_salary(
    lo: int | None, hi: int | None, period: str | None
) -> tuple[int | None, int | None, str | None]:
    """Return (min, max, note) with anything we cannot stand behind removed."""
    floor = MONTHLY_FLOOR if period == "monthly" else ANNUAL_FLOOR
    top = hi if hi is not None else lo
    if top is not None and top < floor:
        # The whole pair is in the wrong unit; neither number means what it claims.
        return None, None, "ats_range_below_plausible_floor"
    note = None
    if lo == 0:
        lo, note = None, "ats_reported_zero_minimum"
    elif lo and hi and hi / lo > MAX_RANGE_RATIO:
        lo, note = None, "ats_min_and_max_in_different_units"
    return lo, hi, note



def _salary_is_usable():
    """SQL twin of `usable_salary`'s floor test, so a filter and the payload agree.

    Without this, `require_stated_salary` returns rows whose published salary we then blank
    out, which is the worst of both: the caller asked to see only stated pay and got a row
    with none.
    """
    top = func.coalesce(Job.salary_max, Job.salary_min)
    return case(
        (Job.salary_period == "monthly", top >= MONTHLY_FLOOR),
        else_=top >= ANNUAL_FLOOR,
    )

# --- serialization ------------------------------------------------------------
def role_group(company_id: str, title: str) -> str:
    """Stable id shared by the same role posted in several cities.

    Employers routinely list one role once per location: MongoDB carries 22 live copies of
    "Enterprise Account Executive, Growth", Databricks 15 of one FDE role. Those rows are all
    genuinely distinct — different job_id, different apply_channel, different city — so we do
    NOT collapse them; a candidate with a visa or relocation constraint needs them apart.

    But nothing in the payload said they were siblings, so a client agent had to guess from
    string equality. It pays for that: ~20% of a `limit` budget goes to rows it already has
    (measured, stable across limit 5/10/20/50), and there is no way to ask for "more, but
    different". This field is the missing signal — group by it in one pass, then spend the
    rest of the budget on distinct roles.

    Grouping is exact on (company, case-folded title). Deliberately no clever stripping of
    trailing city names: that would merge only 1.4% more rows while risking merges of roles
    that are actually different. Predictable beats clever when the consumer is a machine.
    """
    norm = re.sub(r"\s+", " ", (title or "").strip().casefold())
    key = f"{company_id} :: {norm}"
    return "rg_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def job_posting(job: Job, company: Company | None, requested_skills: list[str], now: dt.datetime) -> dict:
    """schema.org/JobPosting + the five OpenHire fields (protocol contract)."""
    mq = match_quality(requested_skills, job.skills)
    fr = freshness(_freshness_anchor(job), now)
    # datePosted is the employer's REAL posting date (ATS), not our crawl date; fall back
    # to first_seen_at only when the ATS exposed no date. days_open = age of the posting.
    posted = _aware(job.posted_at) or _aware(job.first_seen_at)
    _rs, _regions = classify_remote(job.remote_policy, job.location)
    _sal_lo, _sal_hi, _sal_note = usable_salary(
        job.salary_min, job.salary_max, getattr(job, "salary_period", None)
    )
    _apply_ok = apply_url_is_trusted(job.apply_channel)
    return {
        "@type": "JobPosting",
        "job_id": job.id,
        "title": job.title,
        "company": company.name if company else job.company_id,
        "company_id": job.company_id,
        # Same role, several cities → same role_group. See role_group() above.
        "role_group": role_group(job.company_id, job.title),
        "datePosted": posted.date().isoformat() if posted else None,
        "days_open": (now.date() - posted.date()).days if posted else None,
        # Present only when the employer's ATS or mirror reports NO posting date at all
        # (Li Auto's first-party API carries none). datePosted and days_open above are
        # then anchored on the day WE first saw the row, and a reader must not take them
        # for the employer's own date. Same shape as update_signal below, and same rule:
        # this names a limit of the source, not a fact about the employer.
        **({"date_signal": "not_reported_by_ats"} if job.posted_at is None else {}),
        "location": job.location,
        "remote_policy": job.remote_policy,
        "remote_scope": _rs,          # worldwide | region_locked | country_locked | null
        "eligible_regions": _regions,  # matched regions/countries ([] = worldwide/unknown)
        "role_family": getattr(job, "role_family", None),  # populated for ~99% of live rows
        "skills": list(job.skills or []),
        "salary_min": _sal_lo,
        "salary_max": _sal_hi,
        "salary_currency": job.salary_currency if (_sal_lo or _sal_hi) else None,
        # Present only when we dropped something, and it names WHICH shape we hit, so a
        # caller can tell "the employer did not say" from "their ATS said something
        # impossible".
        **({"salary_note": _sal_note} if _sal_note else {}),
        # The period the employer published the figure in — without it a monthly CNY
        # number is indistinguishable from an annual one.
        "salary_period": getattr(job, "salary_period", None) or "annual",
        "salary_inferred": job.salary_inferred,
        # ---- the five OpenHire protocol fields ----
        "verified_at": _aware(job.verified_at).isoformat() if job.verified_at else None,  # ①
        "source": job.source,                                                             # ②
        "ghost_score": round(job.ghost_score, 4) if job.ghost_score is not None else None,  # ③
        # Not a protocol field — a plain-language gloss on ③, because ① and ③ can both be
        # true at once ("confirmed live today" + "open for a year") and the pair reads as a
        # contradiction without it.
        # The employer's own last-touched timestamp. Only some ATSes report one: Greenhouse
        # and Moka do (91% / 96% of their rows differ from posted_at), while Ashby, Lever and
        # Beisen return the posting date again (0% / 0% / 3%). When it merely echoes
        # posted_at we must NOT present it as "last touched", because "untouched for 368
        # days" would then describe the vendor's API rather than the employer, and it reads
        # as an accusation. Null here means "this ATS does not report it", never "abandoned".
        # Honest limit even when real: an ATS bumps it on any edit or re-publish, so it means
        # "touched", not necessarily "content changed".
        **(
            {
                "updated_at": _aware(job.updated_at).isoformat(),
                "days_since_update": int(
                    (now - _aware(job.updated_at)).total_seconds() // 86400
                ),
            }
            if (job.updated_at and job.posted_at
                and _aware(job.updated_at) != _aware(job.posted_at))
            else {"updated_at": None, "days_since_update": None,
                  "update_signal": "not_reported_by_ats"}
        ),
        # What the employer said about THIS role, if they claimed and said anything. It sits
        # beside ghost_score and never on it: the score is a locked pure function, and a
        # claim that could move it would be a ranking parameter you can buy by other means.
        # Absent for the overwhelming majority of rows, which is the honest default.
        **(
            {"employer_correction": _corr}
            if (_corr := employer_correction(job.company_id, job.title))
            else {}
        ),
        "ghost_reason": (
            # Mirror the anchor the pipeline actually scored against: the employer's own
            # posting date when the ATS gives one, else the day we first saw it. Using
            # first_seen_at unconditionally would narrate "open 48d" next to a stored 1.0,
            # which is a worse answer than staying silent.
            ghost_reason(
                job.relist_count or 0,
                (now - _aware(job.posted_at or job.first_seen_at)).total_seconds() / 86400.0,
            )
            if (job.posted_at or job.first_seen_at) else None
        ),
        # ④ The employer's own commitment. Falls back to what they declared for the whole
        # company when they claimed it, so a claim covers roles posted afterwards too.
        # Null means "no employer has claimed this tenant" — never "we could not work it
        # out", because working it out is not something we are able or willing to do.
        "response_sla_days": (
            job.response_sla_days
            if job.response_sla_days is not None
            else (company.response_sla_days if company is not None else None)
        ),
        # ⑤ — but only if it still points at an ATS host we recognise. This string came
        # from a third party's API and an agent may open it, so an unrecognised host is
        # reported rather than handed over. See ats.base.apply_url_is_trusted.
        "apply_channel": job.apply_channel if _apply_ok else None,
        **({} if _apply_ok else {
            "apply_channel_blocked": job.apply_channel,
            "apply_channel_note": (
                "This employer's ATS returned an apply URL on a host we do not recognise, "
                "so it is reported instead of offered. Open it only after checking it "
                "yourself, and prefer the company's own careers page."
            ),
        }),
        # ---- ranking transparency (client may re-rank; server sort is fixed) ----
        # WHICH requested skills this row actually carries. A reviewer searched `rust`,
        # got ten rows all titled "Security Engineer", and filed a filter bug; the filter
        # was right and the titles simply did not show the reason. A match_quality of 1.0
        # with no way to see what matched asks the reader to trust a number over their own
        # eyes, and when the two disagree they are right to trust their eyes.
        # Folded on both sides, then reported in the ROW's own spelling: the caller asked
        # for "computer vision", the posting says "computer-vision", and the useful answer
        # is the tag the posting actually carries.
        "matched_skills": sorted(
            tag for tag in (job.skills or [])
            if normalize_skill(tag) in set().union(
                set(), *(expand_skill(x) for x in (requested_skills or []))
            )
        ),
        "match_quality": round(mq, 4),
        "freshness": round(fr, 4),
        "rank_score": round(rank_score(mq, fr), 6),
    }


# --- hard filter + fixed ranking ---------------------------------------------
def _freshness_anchor(job: Job) -> dt.datetime:
    """The employer's clock for ranking: the POSTING date. posted_at when the ATS reports
    one, else the day this index first saw the row, else verified_at (the index build
    time, identical on every row, so it orders nothing and is only the last resort).

    Not updated_at. Ranking on "last touched" put a 470-day-old Motional posting that an
    editor had touched yesterday above a 3-day-old Torc one, and gave 17 Waymo rows aged
    6 to 289 days one identical score because one weekly edit had touched them all. A
    touch is not a posting: the row still reports it as updated_at / days_since_update,
    beside the ranking, never inside it.
    """
    return job.posted_at or job.first_seen_at or job.verified_at


def resolve_company(session: Session, query: str) -> list[Company]:
    """Turn what a caller actually types into company rows.

    Agents ask "what is Unitree hiring?", never "company_id='unitree'". Names in this index
    are bilingual ("宇树科技 Unitree", "小鹏汽车 XPeng"), so a caseless substring over the
    name catches either half, and an exact id match keeps the machine-readable path working.
    Exact hits win outright — otherwise searching "Robotics" would drown a company actually
    named Robotics in every other firm with the word in its name.
    """
    q = (query or "").strip()
    if not q:
        return []
    low = q.casefold()
    rows = list(session.execute(select(Company)).scalars())
    exact = [c for c in rows if c.id.casefold() == low or (c.name or "").casefold() == low]
    if exact:
        return exact
    return [c for c in rows
            if low in c.id.casefold() or low in (c.name or "").casefold()]


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
    offset: int = 0,
    company_ids: list[str] | None = None,
    location: str | None = None,
) -> list[tuple[Job, float]]:
    """Server-side HARD FILTER (skills ∩/∀, remote, salary, freshness window) + FIXED sort.
    Precise re-ranking is intentionally left to the client agent."""
    stmt = select(Job).where(Job.delisted_at.is_(None))

    if company_ids is not None:
        # An empty list means the caller named a company that does not exist. Filtering on
        # an empty IN would be a silent no-op, which is the one answer we must not give.
        stmt = stmt.where(Job.company_id.in_(company_ids))
    if remote is True:
        stmt = stmt.where(Job.remote_policy == "remote")
    if location:
        # A caseless substring over the ATS location text, in either language: "北京",
        # "Beijing", "Remote", "Mountain View". A seeker leaving China could not exclude
        # China-onsite rows and a seeker in Beijing could not keep only Beijing ones.
        stmt = stmt.where(Job.location.ilike(f"%{location.strip()}%"))
    if min_salary is not None:
        # Keep jobs whose stated pay could meet the floor. Unstated pay is KEPT here (it
        # cannot be ruled out) unless require_stated_salary asks to exclude it.
        # min_salary is an ANNUAL floor, so monthly-quoted pay (Chinese portals) is
        # annualised for the comparison only — the stored figures are never rewritten.
        ann_max, ann_min = _annualised(Job.salary_max), _annualised(Job.salary_min)
        stmt = stmt.where(
            (Job.salary_max.isnot(None) & (ann_max >= min_salary))
            | (Job.salary_min.isnot(None) & (ann_min >= min_salary))
            | (Job.salary_min.is_(None) & Job.salary_max.is_(None))
        )
    if require_stated_salary:
        # "Stated" has to mean stated in a figure we will actually publish. A row we blank
        # out at read time is not stated pay, however many numbers its ATS returned.
        stmt = stmt.where(
            (Job.salary_min.isnot(None) | Job.salary_max.isnot(None)) & _salary_is_usable()
        )
    if currency:
        # A currency filter is meaningful only for stated pay → excludes unstated.
        stmt = stmt.where(Job.salary_currency == currency.upper(), _salary_is_usable())
    if since is not None:
        stmt = stmt.where(Job.first_seen_at > since)

    # Separator-insensitive and alias-aware on the request side (see expand_skill): a
    # requested skill matches a row when ANY of its spellings is on the row.
    req_sets = [expand_skill(x) for x in (skills or []) if x]
    required_sets = [expand_skill(x) for x in (required_skills or []) if x]
    rf = (role_family or "").lower() or None

    scored: list[tuple[Job, float]] = []
    for job in session.execute(stmt).scalars():
        job_skills = {normalize_skill(x) for x in (job.skills or [])}
        if req_sets and not any(aliases & job_skills for aliases in req_sets):
            continue  # ANY-overlap (skills 交集)
        if required_sets and not all(aliases & job_skills for aliases in required_sets):
            continue  # AND — every required skill must be present
        if remote_scope:
            scope, _ = classify_remote(job.remote_policy, job.location)
            if scope != remote_scope:
                continue
        # A row whose role_family is still null has not been classified yet; the newest
        # postings are exactly the ones the weekly classifier has not reached. Excluding
        # them hid a 19-day Torc BEV role from a watch on role_family="engineering". A
        # filter excludes rows known to be OTHER families, never rows we have not read.
        jrf = (getattr(job, "role_family", None) or "").lower()
        if rf and jrf and jrf != rf:
            continue
        mq = match_quality(list(skills or []) or list(required_skills or []), job.skills)
        fr = freshness(_freshness_anchor(job), now)
        scored.append((job, rank_score(mq, fr)))

    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[offset:offset + limit]


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
    offset: int = 0,
    company: str | None = None,
    collapse_role_group: bool = False,
    location: str | None = None,
) -> list[dict]:
    now = _now(now)
    # The page cap. Asking for 200 has always returned 100, and said nothing about it:
    # a reviewer pulled `company=XPeng limit=200`, got 100 of 198, and concluded the index
    # only held 100 XPeng jobs. Then a skill search surfaced two XPeng roles that were not
    # in "the full list", which reads as a consistency bug and is really the same silent
    # cut. `offset` reaches the rest, but nothing told them to page.
    if int(limit) < 1:
        # limit=0 used to return one row, which hid a client bug behind a plausible answer.
        # A negative offset still clamps to 0 (tested, deliberate): asking before the start
        # means the start.
        raise OpenHireError("ERR_BAD_PAGE", f"limit must be >= 1 (got limit={limit}).")
    limit = min(int(limit), MAX_PAGE_SIZE)
    offset = max(0, int(offset))
    company_ids = None
    if company:
        company_ids = [c.id for c in resolve_company(session, company)]
    ranked = _filter_and_rank(
        session, skills, remote, min_salary, None, limit, now,
        required_skills=required_skills, currency=currency,
        require_stated_salary=require_stated_salary, remote_scope=remote_scope,
        role_family=role_family, offset=offset, company_ids=company_ids,
        location=location,
    )
    company_ids = {j.company_id for j, _ in ranked}
    companies = {
        c.id: c
        for c in session.execute(select(Company).where(Company.id.in_(company_ids))).scalars()
    } if company_ids else {}
    # The SAME list the ranker scored with. Passing only `skills` here meant a caller who
    # used required_skills alone got match_quality 1.0 on every row — the neutral value for
    # "nothing was requested" — while the ranking had used the required set. The number
    # shown was not the number that ordered the list.
    scored_against = list(skills or []) or list(required_skills or [])
    rows = [job_posting(j, companies.get(j.company_id), scored_against, now) for j, _ in ranked]
    if collapse_role_group:
        # Keep the highest-ranked row per group and say how many it stands for. The siblings
        # are NOT hidden state: `role_group` still identifies the group, so a caller that
        # needs every city can re-ask with collapse_role_group=false.
        seen: dict[str, dict] = {}
        counts: dict[str, int] = {}
        for r in rows:
            g = r.get("role_group") or r["job_id"]
            counts[g] = counts.get(g, 0) + 1
            seen.setdefault(g, r)
        rows = []
        for g, r in seen.items():
            r = dict(r)
            r["role_group_size"] = counts[g]
            rows.append(r)
    return rows


def skill_diagnostics(
    session: Session, skills: list[str] | None, required_skills: list[str] | None
) -> tuple[list[str], dict[str, list[str]]]:
    """Which requested tags exist nowhere in the live index, and what they might have
    meant. Alias-aware: 感知 is not unknown when the index tags perception. Used on empty
    results AND on non-empty ones: a search that half-matched used to return rows and stay
    silent about the words it dropped. One pass over the live tag vocabulary."""
    vocab: set[str] = set()
    for row in session.execute(
        select(Job.skills).where(Job.delisted_at.is_(None))
    ).scalars():
        for sk in (row or []):
            if sk:
                vocab.add(sk)
    # Folded, or we would tell someone their tag "exists nowhere in the index" when the
    # index simply spells it with the other separator.
    lowered = {normalize_skill(v): v for v in vocab}

    wanted = [t for t in {*(skills or []), *(required_skills or [])} if t]
    unknown, suggestions = [], {}
    for tag in wanted:
        low = normalize_skill(tag)
        if expand_skill(tag) & set(lowered):
            continue  # some spelling of it exists in the index
        unknown.append(tag)
        # Substring hits first — the index tags "kubernetes operators" but not plain
        # "kubernetes", so a substring match points at the real tag where fuzzy distance
        # would not. Then difflib for genuine misspellings. Two-character tags are dropped:
        # they match almost anything and are noise to a caller.
        subs = sorted(
            (orig for lo, orig in lowered.items() if len(lo) > 2 and low in lo),
            key=lambda x: (len(x), x),
        )
        fuzzy = difflib.get_close_matches(low, [lo for lo in lowered if len(lo) > 2],
                                          n=5, cutoff=0.72)
        close: list[str] = []
        for cand in [*subs, *(lowered[f] for f in fuzzy)]:
            if cand not in close:
                close.append(cand)
        if close:
            suggestions[tag] = close[:5]
    return unknown, suggestions


def diagnose_empty_search(
    session: Session,
    skills: list[str] | None = None,
    required_skills: list[str] | None = None,
    role_family: str | None = None,
    currency: str | None = None,
    company: str | None = None,
) -> dict:
    """Explain an empty result set so the caller can tell a typo from a genuine miss.

    A bare `[]` is the same answer to two very different questions: "is anyone hiring for
    this?" and "did I spell the tag right?". A human re-reads their own command; an agent
    cannot, so it either gives up or retries the identical query. This returns the one fact
    that separates the cases — whether each requested tag exists anywhere in the live index
    — plus near-misses to retry with.

    Kept out of `search_jobs`, which always returns a list. Only the MCP boundary swaps in
    this shape, and only when the list came back empty.
    """
    # An empty INDEX explains an empty result on its own, and every other diagnosis below
    # would be actively misleading: with no rows to scan, every tag the caller asked for
    # looks "unknown" and we would tell them to fix a spelling that was never wrong. A new
    # CLI user got "no matches" for "you have no index yet" — the same failure shape we
    # keep finding elsewhere, where a missing prerequisite reads as a genuine answer.
    if not session.scalar(select(func.count()).select_from(Job)):
        return {
            "results": [],
            "matched": 0,
            "index_empty": True,
            "hint": (
                "There is no job index on this machine yet, so this is not a miss: there was "
                "nothing to search. Run `ohp bootstrap` to download the public snapshot "
                "(~25 MB, no account), or start the MCP server with `ohp serve`, which fetches "
                "it by itself on first run. "
                "本机还没有职位索引，所以这不是「没找到」，是「没得找」。跑 `ohp bootstrap` "
                "下载公开快照（约 25 MB，无需注册），或直接 `ohp serve`，服务器会自己拉。"
            ),
            "filters_applied": {
                k: v for k, v in {
                    "company": company, "skills": skills,
                    "required_skills": required_skills,
                    "role_family": role_family, "currency": currency,
                }.items() if v
            },
        }

    # A company that does not resolve explains the empty list by itself, and no amount of
    # tag advice helps — answer that first and stop.
    if company:
        matched = resolve_company(session, company)
        if not matched:
            known = not_indexed.lookup(company)
            if len(known) == 1:
                # Not a typo and not a gap we are unaware of: an employer we know, whose
                # portal we deliberately do not read. Say exactly that, with where to go
                # instead and what would change it, rather than the generic hint. Only
                # when exactly one entry matched: the structured answer names ONE portal
                # and ONE reason, and with several candidates it would be about the
                # first, which the caller never asked for. Several matches take the
                # generic path below with the candidates listed, so the caller re-asks.
                return {
                    "results": [],
                    "matched": 0,
                    "hint": known_not_indexed_hint(known),
                    "known_not_indexed": [e.as_dict() for e in known],
                    "unknown_companies": [company],
                    "suggestions": {},
                    "filters_applied": {
                        k: v for k, v in {
                            "company": company, "skills": skills,
                            "required_skills": required_skills,
                            "role_family": role_family, "currency": currency,
                        }.items() if v
                    },
                }
            names = sorted(
                (c.name for c in session.execute(select(Company)).scalars() if c.name),
                key=str.casefold,
            )
            close = difflib.get_close_matches(company, names, n=5, cutoff=0.55)
            if not close:
                low = company.casefold()
                close = [n for n in names if low[:3] and low[:3] in n.casefold()][:5]
            if len(known) > 1:
                # Several employers we know but do not index match this text. List them
                # and let the caller pick one; the structured answer above is per employer.
                candidates = [e.name for e in known]
                hint = (
                    f"{company!r} matches {len(known)} employers we know but deliberately do "
                    f"not index ({', '.join(candidates)}): their careers sites run on Feishu "
                    "Recruitment, whose job-list API requires a request signature we treat as "
                    "access control. Re-ask with one of them by name for its portal and the "
                    "employer opt-in path; dropping the company filter will not find any of them."
                )
            else:
                candidates = close
                hint = (
                    f"This index has no company matching {company!r}. It covers 139 employers, "
                    "not the whole market, so the company is most likely simply not indexed: "
                    + ("retry with one of unknown_companies' suggestions, or drop the company filter."
                       if close else
                       "drop the company filter to search the whole index, or check the employer "
                       "list at github.com/gzchenhao/openhire.")
                )
            return {
                "results": [],
                "matched": 0,
                "hint": hint,
                "unknown_companies": [company],
                "suggestions": {company: candidates} if candidates else {},
                "filters_applied": {
                    k: v for k, v in {
                        "company": company, "skills": skills,
                        "required_skills": required_skills,
                        "role_family": role_family, "currency": currency,
                    }.items() if v
                },
            }

    unknown, suggestions = skill_diagnostics(session, skills, required_skills)


    if unknown:
        hint = (
            f"No live posting is tagged {unknown!r}. That tag does not exist in this index, "
            "so this is almost certainly a spelling or naming mismatch rather than a dry "
            "market — retry with one of the suggestions, or drop the tag."
        )
    else:
        hint = (
            "Every tag you asked for exists in the index, so the tags are fine: this "
            "combination of filters genuinely has no live match right now. Loosen one "
            "filter at a time (required_skills is the strictest — it is AND, not OR)."
        )
        if company:
            hint = (
                f"{company!r} is in the index, but none of its live postings match the rest "
                "of these filters. Drop the other filters to see everything it has open."
            )
    return {
        "results": [],
        "matched": 0,
        "hint": hint,
        "unknown_skills": unknown,
        "suggestions": suggestions,
        "filters_applied": {
            k: v for k, v in {
                "company": company, "skills": skills,
                "required_skills": required_skills,
                "role_family": role_family, "currency": currency,
            }.items() if v
        },
    }


def known_not_indexed_hint(known: list["not_indexed.NotIndexedEmployer"]) -> str:
    """One sentence a seeker can act on: where the postings actually are, why they are
    not here, and that the employer (not the seeker) holds the key to changing that."""
    first = known[0]
    where = (
        f"Its postings are on its own careers portal at {first.careers_url}, so send the "
        "user there directly."
        if first.careers_url else
        "We have not confirmed its careers portal URL, so do not guess one."
    )
    return (
        f"{first.name} is known to us but deliberately NOT in this index: {first.reason} "
        f"{where} This is not a typo and dropping the company filter will not find it. "
        "The employer can change this by authorising the read-only Feishu open-platform "
        f"scopes {', '.join(first.employer_opt_in.get('scopes', []))}; see "
        "known_not_indexed[].employer_opt_in."
    )


def known_not_indexed_info(entry: "not_indexed.NotIndexedEmployer") -> dict:
    """The get_company_info shape for an employer we know but do not index.

    Deliberately NOT the indexed shape with zeros in it: there is no ghost_score_avg,
    active_jobs or median_days_open because we hold none of this employer's postings,
    and a zero there would read as a verdict on their hiring.
    """
    out = entry.as_dict()
    out.update({
        "company_id": None,
        "claimed": False,
        "hint": known_not_indexed_hint([entry]),
    })
    return out


# --- company trust signals (aggregate only) ----------------------------------
def get_company_info(session: Session, company_id: str, now: dt.datetime | None = None) -> dict:
    company = session.get(Company, company_id)
    if company is None:
        # search_jobs takes names; this took only ids, and nothing bridged the two. Resolve
        # the same way search does, refusing to guess between several matches.
        matched = resolve_company(session, company_id)
        if len(matched) == 1:
            company = matched[0]
        elif len(matched) > 1:
            names = ", ".join(f"{c.id} ({c.name})" for c in matched[:10])
            raise OpenHireError(
                "ERR_AMBIGUOUS_COMPANY",
                f"{company_id!r} matches {len(matched)} employers: {names}. Re-ask with one id.",
            )
        else:
            known = not_indexed.lookup(company_id)
            if len(known) == 1:
                # A structured answer, not an error: the employer exists, we know their
                # portal, and we know why nothing of theirs is here. There are no trust
                # signals to report because we hold none of their postings, and every
                # aggregate field is absent rather than zero so nobody reads "0 active
                # jobs" as "not hiring".
                return known_not_indexed_info(known[0])
            if len(known) > 1:
                names = ", ".join(f"{e.id} ({e.name})" for e in known)
                raise OpenHireError(
                    "ERR_AMBIGUOUS_COMPANY",
                    f"{company_id!r} matches {len(known)} employers we know but do not "
                    f"index: {names}. Re-ask with one id.",
                )
            raise OpenHireError(
                "ERR_COMPANY_NOT_FOUND",
                f"No company with id or name matching {company_id!r}. Use the company_id "
                "from a search_jobs row, or any part of the employer's name.",
            )
    # From here on every query keys on the resolved id: a caller who typed a name got the
    # right Company row above but, until this line, zeros for its aggregates.
    company_id = company.id

    live = select(Job).where(Job.company_id == company_id, Job.delisted_at.is_(None))
    active_jobs = session.scalar(
        select(func.count()).select_from(live.subquery())
    ) or 0
    ghost_avg = session.scalar(
        select(func.avg(Job.ghost_score)).where(
            Job.company_id == company_id, Job.delisted_at.is_(None)
        )
    )
    # A bare ghost_score_avg of 0.87 reads as "87% of this company is fake", which is not
    # what it measures and is not something we can support. These three companions say what
    # actually drove it, so the number arrives with its own limits attached:
    #   * median_days_open — the input the score is mostly made of;
    #   * relisted_postings — 0 means the score is age ONLY, which is the evergreen case;
    #   * last_touched_reported_by_ats — False (Ashby, Lever, 北森) means we cannot tell a
    #     tended req from an abandoned one for this employer at all, so nobody should read
    #     the average as evidence of neglect.
    days_open = [
        d for (d,) in session.execute(
            select(
                func.julianday(_now(now)) - func.julianday(
                    func.coalesce(Job.posted_at, Job.first_seen_at)
                )
            ).where(Job.company_id == company_id, Job.delisted_at.is_(None))
        ) if d is not None
    ]
    days_open.sort()
    relisted = session.scalar(
        select(func.count()).where(
            Job.company_id == company_id, Job.delisted_at.is_(None), Job.relist_count > 0
        )
    ) or 0
    touch_reported = session.scalar(
        select(func.count()).where(
            Job.company_id == company_id, Job.delisted_at.is_(None),
            Job.updated_at.is_not(None), Job.updated_at != Job.posted_at,
        )
    ) or 0
    # Same rule as the per-row `date_signal`: a row whose source reported no posting date
    # is aged from the day this index first saw it. When that is every live row of an
    # employer (Li Auto's first-party mirror carries no date at all), median_days_open is
    # a lower bound on age and not the employer's own timeline, and the caller should
    # know that before reading ghost_score_avg as anything about this employer.
    dates_missing = session.scalar(
        select(func.count()).where(
            Job.company_id == company_id, Job.delisted_at.is_(None),
            Job.posted_at.is_(None),
        )
    ) or 0

    # Aggregate, anonymous signals ONLY — never any individual candidate data.
    # `claimed` is back, and now it means something: it is true only once an employer has
    # claimed this tenant and we verified them by corporate identity (never by payment).
    # In v0.1 this field was always false, which is a worse-than-useless trust signal, so
    # it was removed until there was a real claim path behind it.
    # `index_built_at` is when this index was last built (a batch timestamp shared across
    # companies), honestly named rather than implying a per-company crawl time.
    return {
        "company_id": company.id,
        "company": company.name,
        "ghost_score_avg": round(ghost_avg, 4) if ghost_avg is not None else None,
        # What the average is made of. A score is a question to ask this employer, never a
        # finding about them.
        "median_days_open": int(days_open[len(days_open) // 2]) if days_open else None,
        "relisted_postings": int(relisted),
        "last_touched_reported_by_ats": bool(touch_reported),
        # False means no live row carries the employer's own posting date, so every
        # days_open here counts from first sight (per-row `date_signal`), a lower bound.
        "posting_dates_reported": int(active_jobs) > int(dates_missing),
        "postings_without_reported_date": int(dates_missing),
        "active_jobs": int(active_jobs),
        "claimed": bool(company.verified),
        "claimed_at": _aware(company.claimed_at).isoformat() if company.claimed_at else None,
        "response_sla_days": company.response_sla_days,
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


_WATCH_FILTER_KEYS = ("skills", "required_skills", "remote", "role_family", "min_salary", "company")


def _clean_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Keep only the whitelisted, non-PII filter keys, and REFUSE keys we do not know.
    A watch registered with {company: "minieye", location: "北京"} used to be accepted and
    silently became a watch on the whole index."""
    # Reject any stray PII keys defensively (red line #1) before anything else.
    leaked = set(filters) & _RESUME_KEYS
    if leaked:
        raise OpenHireError(
            "ERR_PII_NOT_ACCEPTED",
            f"Filters may not contain personal data ({', '.join(sorted(leaked))}). "
            "Only anonymous skills/remote/min_salary are stored.",
        )
    unknown = sorted(set(filters) - set(_WATCH_FILTER_KEYS))
    if unknown:
        raise OpenHireError(
            "ERR_UNKNOWN_FILTER",
            f"Unknown watch filter(s) {unknown}. A watch accepts only "
            f"{', '.join(_WATCH_FILTER_KEYS)}; anything else would be dropped and the watch "
            "would silently cover more than you asked for.",
        )
    allowed = {}
    if filters.get("company"):
        allowed["company"] = str(filters["company"]).strip()
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
    if clean.get("company"):
        # Resolve once, at registration, so an unindexed or ambiguous employer is refused
        # here instead of quietly matching nothing (or everything) every week.
        matched = resolve_company(session, clean["company"])
        if not matched:
            known = not_indexed.lookup(clean["company"])
            if known:
                # Still refused (a watch on an employer we hold nothing of would never
                # fire), but with the real reason and the portal, not "not found".
                raise OpenHireError(
                    "ERR_COMPANY_NOT_FOUND",
                    f"{known[0].name} is known but deliberately not indexed, so a watch on it "
                    f"could never match anything. {known[0].reason} "
                    + (f"Its own careers portal is {known[0].careers_url}." if known[0].careers_url
                       else "We have not confirmed its careers portal URL."),
                )
            raise OpenHireError(
                "ERR_COMPANY_NOT_FOUND",
                f"No employer in this index matches {clean['company']!r}; search_jobs with that "
                "company first to see whether it is indexed.",
            )
        if len(matched) > 1:
            names = ", ".join(f"{c.id} ({c.name})" for c in matched[:10])
            raise OpenHireError(
                "ERR_AMBIGUOUS_COMPANY",
                f"{clean['company']!r} matches {len(matched)} employers: {names}. Name one.",
            )
        clean["company"] = matched[0].name
        clean["company_ids"] = [matched[0].id]
    existing = session.scalar(
        select(func.count()).select_from(Watch).where(
            Watch.fingerprint == fingerprint, Watch.active.is_(True)
        )
    ) or 0
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
        # Two testers who both picked "#p0ny" saw each other's watches. A collision is
        # not PII (there is none to leak) but it is someone else's intent. Say when the
        # tag was already in use so the client can pick a longer one.
        "existing_watches": int(existing),
        "fingerprint_notice": (
            "Persist this fingerprint yourself — the server cannot recover it. "
            "check_watches needs the identical fingerprint to return your matches."
            + (
                f" This fingerprint already had {existing} active watch(es) before this one. If "
                "they are not yours, another client chose the same short tag: use a longer, "
                "random one (12+ characters) and re-register."
                if existing else ""
            )
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
        # Rank the WHOLE standing set, then page it. The old call asked for 20 and then
        # marked the watch notified: everything past row 20 was reported never, and on a
        # broad first pull those 20 were an alphabetical slice, not the best matches.
        ranked_all = _filter_and_rank(
            session, f.get("skills"), f.get("remote"), f.get("min_salary"), since, 100_000, now,
            required_skills=f.get("required_skills"), role_family=f.get("role_family"),
            company_ids=f.get("company_ids"),
        )
        total_matching = len(ranked_all)
        ranked = ranked_all[:MAX_PAGE_SIZE]
        company_ids = {j.company_id for j, _ in ranked}
        companies = {
            c.id: c
            for c in session.execute(
                select(Company).where(Company.id.in_(company_ids))
            ).scalars()
        } if company_ids else {}
        # Same list the ranker scored with (see search_jobs): a watch registered with only
        # required_skills would otherwise report match_quality 1.0 and no matched_skills.
        scored_against = list(f.get("skills") or []) or list(f.get("required_skills") or [])
        matches = [
            job_posting(j, companies.get(j.company_id), scored_against, now)
            for j, _ in ranked
        ]
        total_new += len(matches)
        results.append(
            {
                "watch_id": w.watch_id,
                "since": since.isoformat() if since else None,
                # The first pull has no "since", so it returns the standing backlog rather
                # than an increment. That is intended (nobody has seen any of it yet), but
                # the field is called new_matches, and a caller should not have to infer
                # which of the two it is holding from `since` being null.
                "is_first_pull": since is None,
                "total_matching": total_matching,
                "truncated": total_matching > MAX_PAGE_SIZE,
                "truncation_note": (
                    f"{total_matching} postings match; showing the {MAX_PAGE_SIZE} best-ranked. "
                    "Narrow the watch (required_skills, company) to see the rest; the "
                    "remainder is not re-reported on later pulls."
                ) if total_matching > MAX_PAGE_SIZE else None,
                "baseline": (
                    "Everything matching this watch right now; nothing has been reported "
                    "for it before. Later pulls return only postings first seen after this "
                    "moment."
                ) if since is None else None,
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


# --- refresh one employer (throttled) ----------------------------------------
REFRESH_THROTTLE_HOURS = 6


def refresh_company_index(
    session: Session,
    company: str,
    now: dt.datetime | None = None,
    throttle_hours: int = REFRESH_THROTTLE_HOURS,
) -> dict:
    """Re-crawl ONE employer's ATS on demand, at most once every `throttle_hours`.

    Why one employer and not the index: a full crawl is 20+ minutes, which no MCP client
    will wait for, and 0.4.1 already taught us what a blocking call does to a marketplace
    probe. One employer is ~1 minute.

    Why throttled: our own crawl is a weekly batch we control. Exposing refresh to callers
    turns that into "our users hammering someone else's public endpoint on our behalf", and
    the crawl-boundary rule (reports/020) is ours to keep, not to spend. The throttle is
    checked BEFORE any network call, so a throttled request costs the ATS nothing.

    Returns a dict either way — never raises for the ordinary "too soon" case, because
    "you already have fresh data" is an answer, not an error.
    """
    now = _now(now)
    matched = resolve_company(session, company)
    if not matched:
        return {
            "refreshed": False,
            "reason": "unknown_company",
            "hint": (
                f"This index has no company matching {company!r}. It covers employers whose "
                "public ATS we crawl, not the whole market."
            ),
        }
    if len(matched) > 1:
        # Refusing is the point: a vague word must not fan out into several live crawls.
        return {
            "refreshed": False,
            "reason": "ambiguous_company",
            "candidates": [{"company_id": c.id, "name": c.name} for c in matched[:10]],
            "hint": (
                f"{company!r} matches {len(matched)} employers. Re-ask with one company_id — "
                "this never refreshes several at once."
            ),
        }

    target = matched[0]
    last = _aware(target.last_crawled_at) if target.last_crawled_at else None
    if last is not None:
        age_h = (now - last).total_seconds() / 3600.0
        if age_h < throttle_hours:
            nxt = last + dt.timedelta(hours=throttle_hours)
            return {
                "refreshed": False,
                "reason": "throttled",
                "company_id": target.id,
                "company": target.name,
                "last_refreshed_at": last.isoformat(),
                "next_allowed_at": nxt.isoformat(),
                "hint": (
                    f"{target.name} was refreshed {age_h:.1f}h ago; the limit is one crawl "
                    f"per {throttle_hours}h per employer. The data you already have is that "
                    "fresh — search it rather than waiting."
                ),
            }

    from .pipeline import run_ingest

    stats = run_ingest(company_ids=[target.id], respect_interval=False)
    if stats.companies_crawled == 0 and stats.companies_failed:
        # The crawl did not happen. Reporting "refreshed" here is how a stale index
        # gets published as a fresh one: every counter reads 0, which is exactly what
        # a genuinely unchanged employer looks like. Say the ATS was unreachable, and
        # say how old the data the caller still has actually is.
        return {
            "refreshed": False,
            "reason": "ats_unreachable",
            "company_id": target.id,
            "company": target.name,
            "failed_tenants": list(stats.failed_tenants),
            "last_refreshed_at": last.isoformat() if last else None,
            "data_age_days": (int((now - last).total_seconds() // 86400)
                              if last else None),
            "hint": (
                f"{target.name}'s ATS did not answer, so nothing was re-crawled. The rows "
                "you have are unchanged and carry their original verified_at - treat them "
                "as that old, not as confirmed today."
            ),
        }
    session.expire_all()
    refreshed = session.get(Company, target.id)
    new_last = _aware(refreshed.last_crawled_at) if refreshed and refreshed.last_crawled_at else now
    return {
        "refreshed": True,
        "company_id": target.id,
        "company": target.name,
        "last_refreshed_at": new_last.isoformat(),
        "next_allowed_at": (new_last + dt.timedelta(hours=throttle_hours)).isoformat(),
        "jobs_new": stats.jobs_new,
        "jobs_updated": stats.jobs_updated,
        "jobs_delisted": stats.jobs_delisted,
        "jobs_unchanged": stats.jobs_unchanged,
    }


# --- claim authoring: verify a correction actually matches something ----------
def preview_claim_titles(
    session: Session, company: str, titles: list[str]
) -> dict:
    """Check each declared title against live postings BEFORE the claim is recorded.

    The failure this exists to prevent: an employer writes "机器人算法工程师", their live
    posting is "机器人算法工程师（具身方向）", the declaration matches nothing, and nobody
    ever finds out. A correction that silently does nothing is worse than no correction —
    the employer believes they have been heard.

    Matching is the same normalisation `role_group` uses, so what this reports is exactly
    what the runtime will do.
    """
    from .seed.claims import _norm

    matched = resolve_company(session, company)
    if not matched:
        return {"ok": False, "reason": "unknown_company", "company": company}
    if len(matched) > 1:
        return {"ok": False, "reason": "ambiguous_company",
                "candidates": [{"company_id": c.id, "name": c.name} for c in matched[:10]]}
    target = matched[0]

    live = list(session.execute(
        select(Job.title).where(Job.company_id == target.id, Job.delisted_at.is_(None))
    ).scalars())
    by_norm: dict[str, int] = {}
    for t in live:
        by_norm[_norm(t)] = by_norm.get(_norm(t), 0) + 1

    hits, misses = {}, []
    for raw in titles:
        n = by_norm.get(_norm(raw), 0)
        if n:
            hits[raw] = n
        else:
            misses.append(raw)

    near: dict[str, list[str]] = {}
    if misses:
        originals = sorted({t for t in live})
        for raw in misses:
            key = _norm(raw)
            subs = [t for t in originals if key and key in _norm(t)]
            fuzzy = difflib.get_close_matches(raw, originals, n=4, cutoff=0.6)
            cand: list[str] = []
            for c in [*subs, *fuzzy]:
                if c not in cand:
                    cand.append(c)
            if cand:
                near[raw] = cand[:4]

    return {
        "ok": not misses,
        "company_id": target.id,
        "company": target.name,
        "live_postings": len(live),
        "matched": hits,
        "unmatched": misses,
        "did_you_mean": near,
    }
