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

from sqlalchemy import delete, case, func, or_, select
from sqlalchemy.orm import Session

from .db import Application, Company, Job, Watch
from .errors import OpenHireError
from .ats import apply_url_is_trusted
from .pipeline.ghost_score import ghost_reason
from .seed.claims import employer_correction
from .seed import not_indexed
from .pipeline.extract import (
    ROLE_FAMILIES, SENIORITY_ALIASES, SENIORITY_LEVELS, classify_role_family_heuristic,
    expand_seniority, requirements_from_text, seniority_from_title,
)
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
# Below this a fingerprint is flagged as short (never refused: older clients send "#a3f9").
MIN_FINGERPRINT_LEN = 8


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

# --- location aliases ---------------------------------------------------------
# The ATS location text is whatever the employer typed, and Chinese employers type it
# three ways: "北京市", "广东·天河区" (province plus district, city omitted), and "Beijing".
# A plain substring on 广州 found nothing while 天河区 found 136 rows, and "Beijing" reached
# three MongoDB rows in English and none of the 185 rows spelled 北京市. Each row below is
# one place under every spelling a seeker or an employer uses for it. Matching is an OR of
# caseless substrings over the whole group when the query IS one of its members; any other
# query stays the plain substring it always was, so "Mountain View" still works.
_LOCATION_GROUPS: tuple[tuple[str, ...], ...] = (
    ("广州", "guangzhou", "广州市", "天河区", "番禺区", "黄埔区", "南沙区", "海珠区", "越秀区", "白云区"),
    ("北京", "beijing", "北京市"),
    ("上海", "shanghai", "上海市"),
    ("深圳", "shenzhen", "深圳市", "南山区", "福田区", "龙岗区", "宝安区"),
    ("杭州", "hangzhou", "杭州市"),
    ("苏州", "suzhou", "苏州市"),
    ("南京", "nanjing", "南京市"),
    ("武汉", "wuhan", "武汉市"),
    ("成都", "chengdu", "成都市"),
    ("合肥", "hefei", "合肥市", "包河区"),
    ("remote", "远程"),
    # Round 9 (an HR persona, base Hong Kong, reports/055): "Hong Kong" reached three rows
    # spelled in English and none of the five spelled 香港·九龙区; "香港" the reverse. One
    # place, two answers. The rest are the cities the index actually carries under one
    # spelling only, so the other language reaches them too.
    # Boards also write a Hong Kong district or the airport code alone ("Sheung Wan, HKG":
    # Atoms, 2026-10-21, reports/086). English district names and traditional spellings only:
    # the simplified 九龙 / 沙田 / 大埔 are also places in Chongqing, Dongguan and Meizhou.
    ("香港", "hong kong", "hongkong", "hong kong sar", "hksar", "香港特别行政区", "hkg",
     "kowloon", "sheung wan", "sha tin", "tai po", "kwun tong", "wan chai", "tsim sha tsui",
     "causeway bay", "quarry bay", "cyberport", "九龍", "灣仔", "觀塘", "銅鑼灣", "尖沙咀", "數碼港"),
    ("澳门", "macau", "macao"),
    ("台北", "taipei"),
    ("新加坡", "singapore"),
    ("东京", "tokyo"),
    ("伦敦", "london"),
    ("慕尼黑", "munich", "münchen"),
    ("长沙", "changsha", "长沙市"),
    ("天津", "tianjin", "天津市"),
    ("重庆", "chongqing", "重庆市"),
    ("青岛", "qingdao", "青岛市"),
    ("厦门", "xiamen", "厦门市"),
    ("无锡", "wuxi", "无锡市"),
    ("东莞", "dongguan", "东莞市"),
    ("佛山", "foshan", "佛山市"),
    ("宁波", "ningbo", "宁波市"),
    ("郑州", "zhengzhou", "郑州市"),
    ("沈阳", "shenyang", "沈阳市"),
    ("常州", "changzhou", "常州市"),
    ("福州", "fuzhou", "福州市"),
    ("嘉兴", "jiaxing", "嘉兴市"),
)

# Regions a seeker names that no posting spells out: rows say "Palo Alto" or "上海市", never
# "Bay Area" or "China". A query for the region matches any of its places (persona test,
# 2026-10-30: "China" returned nothing and an assistant ran eight searches for the Bay Area).
# Plain 湾区 is left out: in Chinese it as often means the Guangdong-Hong Kong-Macao one.
_MAINLAND_GROUPS = ("广州", "北京", "上海", "深圳", "杭州", "苏州", "南京", "武汉", "成都", "合肥", "长沙", "天津",
                    "重庆", "青岛", "厦门", "无锡", "东莞", "佛山", "宁波", "郑州", "沈阳", "常州", "福州", "嘉兴")
_REGION_QUERIES: dict[str, tuple[str, ...]] = {
    **{q: ("china", "中国", "prc") for q in ("china", "中国", "全国", "中国大陆", "mainland china", "prc")},
    **{q: ("bay area", "san francisco", "palo alto", "mountain view", "sunnyvale", "san jose",
           "menlo park", "redwood city", "santa clara", "san mateo", "foster city", "burlingame",
           "south san francisco", "cupertino", "fremont", "oakland", "berkeley", "emeryville", "milpitas",
           "los altos", "san carlos", "belmont", "hayward", "san bruno")
       for q in ("bay area", "sf bay area", "san francisco bay area", "旧金山湾区", "硅谷", "silicon valley")},
}

# Abbreviations a seeker types that must never be used as a match pattern: "hk" as a
# substring is also the middle of Tashkent. They resolve to a group and are not in it.
_LOCATION_QUERY_SYNONYMS = {"hk": "香港", "sg": "新加坡"}


def location_aliases(query: str) -> list[str]:
    """Every spelling to match for a location query. Always contains the query itself."""
    q = " ".join((query or "").casefold().split())
    if not q:
        return []
    q = _LOCATION_QUERY_SYNONYMS.get(q, q)
    if q in _REGION_QUERIES:
        out = list(_REGION_QUERIES[q])
        if q in ("china", "中国", "全国", "中国大陆", "mainland china", "prc"):
            for group in _LOCATION_GROUPS:
                if group[0] in _MAINLAND_GROUPS:
                    out.extend(group)
        return list(dict.fromkeys(out))
    for group in _LOCATION_GROUPS:
        if q in {m.casefold() for m in group}:
            return list(dict.fromkeys(group))
    return [query.strip()]


def _location_clause(query: str):
    """SQL: the row's location text contains any alias of `query`, caselessly."""
    return or_(*(Job.location.ilike(f"%{alias}%") for alias in location_aliases(query)))


# --- title filter ---------------------------------------------------------------
# Skill tags and role_family describe engineering well and the rest of a company badly. An
# HR persona (reports/055) could not isolate recruiting roles at all: there is no HR family
# (they file under ops), no skill tag says "recruiter", and paging every employer at
# limit 10 missed Dobot's HRBP and Pudu's 招聘经理, which the agent then reported as
# "Chinese embodied companies post no HR roles". The title is the one field every posting
# has that names the job. An ASCII term must start a word ("hr" reaches HR, HRBP and HR
# Business Partner, not Chrome); a CJK term is a plain substring, except where a common
# compound swallows it (人事 inside 机器人事业部, "robotics business unit"). The HR family
# (role_family="hr" since 0.8.17) is the one group of synonyms we expand: a title search
# also reaches rows classified before the family existed.
_TITLE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("hr", "hrbp", "human resources", "recruit", "talent acquisition", "talent partner",
     "sourcer", "people operations", "people ops", "people partner", "people lead",
     "people business partner", "head of people", "chief people", "人力", "人事", "招聘"),
)


def expand_title_term(term: str) -> list[str]:
    """Every spelling to match for one title term. Always contains the term itself."""
    t = " ".join((term or "").casefold().split())
    if not t:
        return []
    for group in _TITLE_GROUPS:
        if t in group:
            return list(group)
    return [t]


# CJK aliases that sit inside an unrelated compound, with what must not follow them.
_CJK_NOT_FOLLOWED_BY = {"人事": "业"}


def _title_pattern(alias: str) -> re.Pattern[str]:
    if re.search(r"[^\x00-\x7f]", alias):
        tail = _CJK_NOT_FOLLOWED_BY.get(alias)
        return re.compile(re.escape(alias) + (f"(?!{tail})" if tail else ""), re.IGNORECASE)
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias), re.IGNORECASE)


def title_terms(title: str | list[str] | None) -> list[str]:
    """Normalise the `title` argument: one string or a list, blanks dropped."""
    if title is None:
        return []
    items = [title] if isinstance(title, str) else list(title)
    return [t for t in (" ".join(str(x).split()) for x in items) if t]


def title_matches(title: str | None, terms: list[str]) -> bool:
    """True when the title contains any alias of ANY term (OR across terms)."""
    text = title or ""
    return any(
        _title_pattern(alias).search(text)
        for term in terms
        for alias in expand_title_term(term)
    )


# What people and agents call the HR family; resolved to it rather than refused.
ROLE_FAMILY_ALIASES = {
    "recruiting": "hr", "recruitment": "hr", "recruiter": "hr", "talent": "hr",
    "talent acquisition": "hr", "people": "hr", "people ops": "hr", "human resources": "hr",
    "human_resources": "hr", "招聘": "hr", "人力资源": "hr", "人事": "hr", "人力": "hr",
}


def check_role_family(role_family: str | None) -> str | None:
    """A role_family the taxonomy does not have is refused, not ignored.

    `role_family="recruiting"` used to pass straight through and return the whole index
    (Waymo engineers, on a search for HR jobs): the filter only excluded rows whose family
    was a DIFFERENT known value, and "recruiting" differed from all of them. The silent
    no-op then read as "OpenHire has no HR roles". Since 0.8.17 the taxonomy has an "hr"
    family and the names people use for it (recruiting, people, 招聘…) resolve to it; any
    other unknown value is still refused with the valid list.
    """
    rf = " ".join((role_family or "").strip().lower().split()) or None
    if rf in ROLE_FAMILY_ALIASES:
        rf = ROLE_FAMILY_ALIASES[rf]
    if rf and rf not in ROLE_FAMILIES:
        raise OpenHireError(
            "ERR_UNKNOWN_ROLE_FAMILY",
            f"role_family {role_family!r} is not a family this index uses. Valid values: "
            f"{', '.join(ROLE_FAMILIES)} (recruiting / talent / people / HRBP / 招聘 roles are "
            "'hr'). For a role no family names, filter on the title instead, e.g. "
            "title=['招聘'] or title=['finance'].",
        )
    return rf


# --- last-touched provenance --------------------------------------------------
# Vendors whose API carries a last-touched field of its own, distinct from the posting
# date (Greenhouse `updated_at` vs `first_published`, Moka `updatedAt` vs `publishedAt`).
# For these an updated_at equal to posted_at is a fact ("published, not edited since").
# Ashby and Lever expose no such field; Beisen's ChangeDate echoes PostDate on 97% of
# rows, so for it and everything else equality is read as "not reported".
TOUCH_REPORTING_VENDORS = frozenset({"greenhouse", "moka"})


def check_posted_within_days(value) -> int | None:
    """1 to 365, or None. A typo like 0 or -3 is refused rather than read as "no limit"."""
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= 365:
        raise OpenHireError("ERR_BAD_QUERY", f"posted_within_days must be a whole number from 1 to 365 (got {value!r}).")
    return n


def is_entry_level(title: str | None, description: str | None) -> bool:
    """Open to a new graduate: the posting says campus / intern / no experience needed, or
    its title names an intern or junior level. A posting that says nothing either way is
    left out: entry_level is the filter a 应届生 uses to stop scrolling past 5-year roles,
    and "might be" is what they already had (reports/110)."""
    level = seniority_from_title(title)
    if level in ("lead", "manager", "director", "staff"):
        return False
    entry = requirements_from_text(title, description)["entry_level"]
    if entry is not None:
        # The posting's own words win: "Associate Technician, 2+ years" is not entry level.
        return entry
    return level in ("intern", "junior")


def check_sector(value: str | None) -> str | None:
    """Validate a sector filter; unknown words are refused, like role_family, so "robtics" never
    reads as "every employer"."""
    if value is None or str(value).strip() == "":
        return None
    from .seed.sectors import SECTOR_ALIASES, resolve_sector
    out = resolve_sector(value)
    if out is None:
        raise OpenHireError(
            "ERR_UNKNOWN_SECTOR",
            f"Unknown sector {value!r}. Use autonomous_driving (自动驾驶 / 智驾), embodied_ai "
            "(具身 / 机器人), ai_infra (大模型 / AI) or other.",
        )
    return out


def check_seniority(values: list[str] | str | None) -> list[str] | None:
    """Validate a seniority filter: a list of levels or aliases, refused when unknown.

    Like role_family, an unknown value is an error, not a silent no-op: "senoir" returning
    the whole index would read as "every posting matched"."""
    if values is None or values == []:
        return None
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for v in values:
        key = str(v or "").strip().lower()
        if key in SENIORITY_LEVELS or key in SENIORITY_ALIASES:
            out.append(key)
        else:
            raise OpenHireError(
                "ERR_UNKNOWN_SENIORITY",
                f"Unknown seniority {v!r}. Use one or more of {', '.join(SENIORITY_LEVELS)}, "
                "or the aliases ic (intern, junior, senior, staff, unknown) and management "
                "(lead, manager, director).",
            )
    return out or None


def _touch_is_reported(job: Job, company: Company | None) -> bool:
    if not (job.updated_at and job.posted_at):
        return False
    if company is not None and company.ats_vendor in TOUCH_REPORTING_VENDORS:
        return True
    return _aware(job.updated_at) != _aware(job.posted_at)


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


def date_signal_for(job: Job, company: Company | None) -> str | None:
    """The per-row caveat on datePosted, or None when the date is the employer's system's.

    `self_reported`: the employer typed this date into a roster (ats/self_reported.py); an
    ATS date is system-written and cannot be edited, this one can, and the row says so.
    `not_reported_by_ats`: the source carries no date at all, so datePosted is the day this
    index first saw the row.
    """
    if company is not None and getattr(company, "ats_vendor", None) == "self_reported":
        return "self_reported" if job.posted_at is not None else "not_reported_by_ats"
    return "not_reported_by_ats" if job.posted_at is None else None


def _extra_apply_hosts(company: Company | None) -> set[str]:
    """For a self-reported roster, the employer's own verified domain is the one host an
    apply link may be on (ats/self_reported.py); every other vendor has fixed ATS hosts."""
    if company is not None and getattr(company, "ats_vendor", None) == "self_reported":
        from .ats.self_reported import trusted_hosts

        return trusted_hosts(company.id)
    return set()


# --- plain language for the person reading the answer (0.8.30, reports/100) --------------
# A tester read "datePosted" on a Li Auto row as the employer's date (its system reports
# none), took ghost_score for a trust score, and asked for the dates "translated into words
# a normal user understands". These sentences are what the assistant should show; the
# fields stay beside them for anyone who wants the raw values.
LONG_OPEN_DAYS = 90


def _date_source(job: Job, company: Company | None) -> str:
    """employer_ats | employer_self_reported | index_first_seen: plainer than date_signal."""
    ds = date_signal_for(job, company)
    if ds == "self_reported":
        return "employer_self_reported"
    if ds == "not_reported_by_ats":
        return "index_first_seen"
    return "employer_ats"


def dates_in_words(posted_day: dt.date | None, days_open: int | None, source: str,
                   verified_day: dt.date | None, correction: dict | None = None) -> dict:
    """One sentence per language about the dates on a posting, safe to show verbatim.
    Never says a posting is fake, dead or not hiring: it reports what was measured."""
    if posted_day is None or days_open is None:
        return {"zh": "这条岗位没有可用的日期。", "en": "This posting carries no usable date."}
    p = posted_day.isoformat()
    v_zh = f"；最近核验 {verified_day.isoformat()}，雇主系统当天仍返回这条岗位" if verified_day else ""
    v_en = f"; last verified {verified_day.isoformat()}, when the employer's system still returned it" if verified_day else ""
    if source == "index_first_seen":
        zh = f"雇主系统没有提供发布日期；本工具首次发现日期 {p}，在架至少 {days_open} 天{v_zh}。"
        en = (f"The employer's system reports no posting date; this index first saw the posting on {p}, "
              f"so it has been open at least {days_open} days{v_en}.")
    elif source == "employer_self_reported":
        zh = f"雇主自报发布日期 {p}（雇主自己填写的，不是系统记录），在架 {days_open} 天{v_zh}。"
        en = f"Posting date {p} as reported by the employer itself (typed in, not system-recorded), open {days_open} days{v_en}."
    elif source == "board_live":
        zh = f"招聘页自己标的发布日期 {p}，在架 {days_open} 天；本次是现读，不是索引记录。"
        en = f"Posting date {p} as the employer's board shows it, open {days_open} days; read live just now, not from the index."
    else:
        zh = f"雇主发布日期 {p}，在架 {days_open} 天{v_zh}。"
        en = f"Employer posting date {p}, open {days_open} days{v_en}."
    if correction and correction.get("date_semantics") == "requisition_created":
        zh += "雇主说明这个日期是内部立项日，不是上线日，所以在架天数会偏大。"
        en += " The employer says this date is when the requisition was opened internally, not when it went live, so days open overstates."
    if days_open > LONG_OPEN_DAYS:
        zh += "在架较久，投递前建议先确认仍在招。"
        en += " Open for a while now; worth confirming it is still being filled before you apply."
    return {"zh": zh, "en": en}


def check_before_apply(*, date_source: str, days_open: int | None, salary_stated: bool,
                       remote_scope: str | None, apply_ok: bool, correction: dict | None) -> list[dict]:
    """What a reader should confirm before applying, each item from a measured fact.
    An empty list means nothing on this row stood out, not that the posting is vetted."""
    out: list[dict] = []
    if date_source == "index_first_seen":
        out.append({"code": "no_employer_date",
                    "zh": "雇主系统没有提供发布日期，在架天数是从本工具首次发现算起的下限。",
                    "en": "The employer's system reports no posting date; days open counts from when this index first saw it, a lower bound."})
    elif date_source == "employer_self_reported":
        out.append({"code": "self_reported_date",
                    "zh": "发布日期是雇主自己填写的，不是系统记录。",
                    "en": "The posting date was typed in by the employer, not recorded by a system."})
    if days_open is not None and days_open > LONG_OPEN_DAYS:
        out.append({"code": "open_over_90d",
                    "zh": f"在架 {days_open} 天，投递前先确认仍在招。",
                    "en": f"Open {days_open} days; confirm it is still being filled before applying."})
    if not salary_stated:
        out.append({"code": "salary_not_stated",
                    "zh": "雇主没有写薪资。",
                    "en": "The employer states no salary."})
    if remote_scope == "unknown":
        out.append({"code": "remote_scope_unknown",
                    "zh": "标了远程，但哪些地区能申请没有写清。",
                    "en": "Marked remote, but which regions qualify is not stated."})
    if not apply_ok:
        out.append({"code": "apply_link_unrecognised",
                    "zh": "投递链接在本工具不认识的域名上，先从公司官网核对再打开。",
                    "en": "The apply link is on a host this tool does not recognise; check it against the company's own site first."})
    if correction and correction.get("status") == "closed":
        out.append({"code": "employer_says_closed",
                    "zh": "雇主自己说明这个岗位已经关闭，虽然系统仍在返回它。",
                    "en": "The employer itself says this role is closed, although its system still returns it."})
    if correction and correction.get("date_semantics") == "requisition_created":
        out.append({"code": "date_is_requisition_created",
                    "zh": "雇主说明日期是内部立项日，不是上线日。",
                    "en": "The employer says the date is the internal requisition date, not the go-live date."})
    return out


def _sector_of(company_id: str | None) -> str | None:
    from .seed.sectors import sector_of
    return sector_of(company_id)


def job_posting(job: Job, company: Company | None, requested_skills: list[str], now: dt.datetime) -> dict:
    """schema.org/JobPosting + the five OpenHire fields (protocol contract)."""
    mq = match_quality(requested_skills, job.skills)
    fr = freshness(_freshness_anchor(job), now)
    # datePosted is the employer's REAL posting date (ATS), not our crawl date; fall back
    # to first_seen_at only when the ATS exposed no date. days_open = age of the posting,
    # in calendar days, and the SAME number feeds ghost_reason below: the two used to be
    # computed separately (calendar days here, floored elapsed seconds there) and differed
    # by one on every row, "days_open 848" beside "open 847d".
    posted = _aware(job.posted_at or job.first_seen_at)
    age_days = (now.date() - posted.date()).days if posted else None
    _rs, _regions = classify_remote(job.remote_policy, job.location)
    _sal_lo, _sal_hi, _sal_note = usable_salary(
        job.salary_min, job.salary_max, getattr(job, "salary_period", None)
    )
    _apply_ok = apply_url_is_trusted(job.apply_channel, extra_hosts=_extra_apply_hosts(company))
    return {
        "@type": "JobPosting",
        "job_id": job.id,
        "title": job.title,
        "company": company.name if company else job.company_id,
        "company_id": job.company_id,
        # Same role, several cities → same role_group. See role_group() above.
        "role_group": role_group(job.company_id, job.title),
        # The employer's sector (seed/sectors.py): autonomous_driving | embodied_ai | ai_infra |
        # other, or null for a board the user added themselves.
        "sector": _sector_of(job.company_id),
        "datePosted": posted.date().isoformat() if posted else None,
        "days_open": age_days,
        # Present only when the employer's ATS or mirror reports NO posting date at all
        # (Li Auto's first-party API carries none). datePosted and days_open above are
        # then anchored on the day WE first saw the row, and a reader must not take them
        # for the employer's own date. Same shape as update_signal below, and same rule:
        # this names a limit of the source, not a fact about the employer.
        **({"date_signal": _ds} if (_ds := date_signal_for(job, company)) else {}),
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
        # and Moka do (a field of their own, distinct from the posting date), while Ashby
        # and Lever have no such field (the adapters store nothing, and older snapshots
        # carry the posting date copied into this column) and Beisen's ChangeDate equals
        # the posting date on 97% of rows. Where the vendor reports it, an equal timestamp
        # means "published and not edited since" and is shown as such: a row Greenhouse
        # published yesterday used to come back `update_signal: not_reported_by_ats` because
        # nothing had touched it yet, which said the opposite of the truth. Where the
        # vendor does not, or only echoes, we must NOT present it as "last touched", because
        # "untouched for 368 days" would then describe the vendor's API rather than the
        # employer, and it reads as an accusation. Null here means "this ATS does not
        # report it", never "abandoned". Honest limit even when real: an ATS bumps it on
        # any edit or re-publish, so it means "touched", not necessarily "content changed".
        **(
            {
                "updated_at": _aware(job.updated_at).isoformat(),
                "days_since_update": int(
                    (now - _aware(job.updated_at)).total_seconds() // 86400
                ),
            }
            if _touch_is_reported(job, company)
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
            # which is a worse answer than staying silent. Same calendar-day count as
            # days_open, so the two numbers on one row never disagree.
            (ghost_reason(job.relist_count or 0, float(age_days))
             # Counted from the day this index first saw the row when the employer's system
             # gives no date, so the figure is a floor, not the age (persona test, 2026-10-29).
             + (" (at least: counted from the day OpenHire first saw it; the employer's system gives no date)"
                if date_signal_for(job, company) == "not_reported_by_ats" else ""))
            if age_days is not None else None
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
        # ---- plain language (0.8.30): the level the title names, where the date comes
        # from, the dates as a sentence, and what to confirm before applying. _ds and _corr
        # were bound by the walrus expressions above; a dict display evaluates in order.
        "seniority": seniority_from_title(job.title),
        # What the posting itself asks for: lowest required degree, fewest years, campus /
        # intern track (pipeline.extract.requirements_from_text). Read from the text with free
        # rules at read time; null means the posting did not say, not "none required".
        "requirements": requirements_from_text(job.title, job.description_raw),
        "date_source": _date_source(job, company),
        "dates_in_words": dates_in_words(
            posted.date() if posted else None, age_days, _date_source(job, company),
            _aware(job.verified_at).date() if job.verified_at else None, _corr,
        ),
        "check_before_apply": check_before_apply(
            date_source=_date_source(job, company), days_open=age_days,
            salary_stated=bool(_sal_lo or _sal_hi), remote_scope=_rs, apply_ok=_apply_ok,
            correction=_corr,
        ),
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
    title: str | list[str] | None = None,
    seniority: list[str] | None = None,
    sector: str | None = None,
    entry_level: bool = False,
    posted_within_days: int | None = None,
) -> list[tuple[Job, float]]:
    """Server-side HARD FILTER (skills ∩/∀, remote, salary, freshness window) + FIXED sort.
    Precise re-ranking is intentionally left to the client agent."""
    terms = title_terms(title)
    # The level the title names (pipeline.extract.seniority_from_title). A hard filter like
    # the others and never a ranking input: "Senior Manager, Perception Data" outranked every
    # engineer on a perception search because it was the newest, and nothing could keep it out.
    keep_levels = expand_seniority(seniority)
    # Live = not delisted AND returned by the employer's system within 30 days (reports/101).
    stmt = select(Job).where(live_clause(verified_cutoff(session)))

    if company_ids is not None:
        # An empty list means the caller named a company that does not exist. Filtering on
        # an empty IN would be a silent no-op, which is the one answer we must not give.
        stmt = stmt.where(Job.company_id.in_(company_ids))
    if sector:
        from .seed.sectors import company_ids_in
        stmt = stmt.where(Job.company_id.in_(company_ids_in(sector)))
    if remote is True:
        stmt = stmt.where(Job.remote_policy == "remote")
    if location:
        # A caseless substring over the ATS location text, in either language: "北京",
        # "Beijing", "Remote", "Mountain View". A seeker leaving China could not exclude
        # China-onsite rows and a seeker in Beijing could not keep only Beijing ones.
        # Alias-aware for the cities employers spell several ways (see _LOCATION_GROUPS):
        # 广州 also reaches "广东·天河区", Beijing also reaches "北京市".
        stmt = stmt.where(_location_clause(location))
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
    if posted_within_days:
        # By the employer's own posting date, or the day this index first saw a row whose
        # system reports none (the same date days_open counts from). A seeker on Zhihu:
        # "超过14天的岗位往往希望就不是那么大了" (reports/114).
        stmt = stmt.where(func.coalesce(Job.posted_at, Job.first_seen_at) >= now - dt.timedelta(days=int(posted_within_days)))

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
        # "Known" includes what the free title rule is sure of: with 43% of live rows still
        # unclassified (2026-10-19), role_family="hr" otherwise returned mostly engineers.
        # HR is decided by the title alone, so an unclassified row joins an hr search only
        # when its title names an HR job; for any other family an unsure row stays in.
        jrf = (getattr(job, "role_family", None) or "").lower()
        if rf and not jrf:
            jrf = classify_role_family_heuristic(job.title or "") or ("unclassified" if rf == "hr" else "")
        if rf and jrf and jrf != rf:
            continue
        if terms and not title_matches(job.title, terms):
            continue
        if keep_levels is not None and seniority_from_title(job.title) not in keep_levels:
            continue
        if entry_level and not is_entry_level(job.title, job.description_raw):
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
    title: str | list[str] | None = None,
    seniority: list[str] | None = None,
    sector: str | None = None,
    entry_level: bool = False,
    posted_within_days: int | None = None,
) -> list[dict]:
    now = _now(now)
    posted_within_days = check_posted_within_days(posted_within_days)
    role_family = check_role_family(role_family)
    seniority = check_seniority(seniority)
    sector = check_sector(sector)
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
        location=location, title=title, seniority=seniority, sector=sector,
        entry_level=bool(entry_level), posted_within_days=posted_within_days,
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


# --- what counts as live (the maintainer, 2026-10-28, reports/101) ---------------------
# A posting counts as live only while the employer's own system has returned it within the
# last 30 days. When a board moves (four Greenhouse boards 404 since September), the crawl
# leaves the existing rows alone on purpose, so one bad night cannot wipe an employer, and
# those rows used to sit in every search and every published figure: 416 of them, last
# confirmed one to two months earlier. The window is measured back from the newest
# verification in the index being read, not from today's clock, so a copy of the index
# that has not been refreshed for a while is not emptied by the calendar.
STALE_AFTER_DAYS = 30


def verified_cutoff(session: Session) -> dt.datetime | None:
    """Rows verified before this are no longer counted as live; None for an empty index."""
    newest = session.scalar(select(func.max(Job.verified_at)).where(Job.delisted_at.is_(None)))
    if newest is None:
        return None
    if isinstance(newest, str):
        newest = dt.datetime.fromisoformat(newest)
    return _aware(newest) - dt.timedelta(days=STALE_AFTER_DAYS)


def sector_thermometer(session: Session) -> dict:
    """New postings per sector in the 30 days up to the index's newest verification, against
    the 30 days before (reports/110: "which sector is hiring more this month" was a question
    nobody could answer from a job board). Counted by the employer's own posting date, closed
    postings included, so a window is not shrunk by later closures; rows whose system reports
    no posting date are left out of both windows. Anchored to the index, not the wall clock,
    so an old snapshot is not read as a hiring freeze."""
    from .seed.sectors import SECTORS, sector_of
    newest = session.scalar(select(func.max(Job.verified_at)))
    if newest is None:
        return {}
    if isinstance(newest, str):
        newest = dt.datetime.fromisoformat(newest)
    end = _aware(newest)
    mid, start = end - dt.timedelta(days=30), end - dt.timedelta(days=60)
    out = {sec: {"last_30d": 0, "prior_30d": 0} for sec in SECTORS}
    for cid, posted in session.execute(
        select(Job.company_id, Job.posted_at).where(Job.posted_at.isnot(None))
    ):
        sec = sector_of(cid)
        if sec is None:
            continue
        p = _aware(dt.datetime.fromisoformat(posted) if isinstance(posted, str) else posted)
        if mid < p <= end:
            out[sec]["last_30d"] += 1
        elif start < p <= mid:
            out[sec]["prior_30d"] += 1
    for v in out.values():
        v["change_pct"] = round(100 * (v["last_30d"] - v["prior_30d"]) / v["prior_30d"]) if v["prior_30d"] else None
    return {"window_end": end.date().isoformat(), "by_sector": out}


def live_clause(cutoff: dt.datetime | None):
    """The SQL condition for "live": not delisted and verified inside the window."""
    if cutoff is None:
        return Job.delisted_at.is_(None)
    return (Job.delisted_at.is_(None)) & (Job.verified_at >= cutoff)


def live_employer_count(session: Session) -> int:
    """Employers with at least one live posting right now: the `employers_with_live_postings`
    figure of docs/numbers.json, computed from the index being searched. A hint used to say
    "139 employers" as literal text; it was right by accident on the day it was written and
    against rule 1 of the writing rules every day after."""
    return int(session.scalar(
        select(func.count(func.distinct(Job.company_id))).where(live_clause(verified_cutoff(session)))
    ) or 0)


def diagnose_empty_search(
    session: Session,
    skills: list[str] | None = None,
    required_skills: list[str] | None = None,
    role_family: str | None = None,
    currency: str | None = None,
    company: str | None = None,
    title: str | list[str] | None = None,
    location: str | None = None,
    seniority: list[str] | str | None = None,
    sector: str | None = None,
    entry_level: bool = False,
    posted_within_days: int | None = None,
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
    def _applied() -> dict:
        # Every filter the caller sent, so an empty answer can be traced to one of them
        # (persona test, 2026-10-30: location and seniority were missing and the assistant
        # could not tell which one emptied the result).
        return {k: v for k, v in {
            "company": company, "skills": skills, "required_skills": required_skills,
            "role_family": role_family, "currency": currency,
            "title": title_terms(title) or None, "location": (location or "").strip() or None,
            "seniority": ([seniority] if isinstance(seniority, str) else seniority) or None,
            "sector": sector or None,
            "entry_level": True if entry_level else None,
            "posted_within_days": posted_within_days or None,
        }.items() if v}

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
            "status": "index_empty",
            "headline": EMPTY_HEADLINES["index_empty"],
            "hint": (
                "There is no job index on this machine yet, so this is not a miss: there was "
                "nothing to search. Run `ohp bootstrap` to download the public snapshot "
                "(~30 MB, no account), or start the MCP server with `ohp serve`, which fetches "
                "it by itself on first run. "
                "本机还没有职位索引，所以这不是「没找到」，是「没得找」。跑 `ohp bootstrap` "
                "下载公开快照（约 30 MB，无需注册），或直接 `ohp serve`，服务器会自己拉。"
            ),
            "filters_applied": _applied(),
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
                    "status": "known_not_indexed",
                    "headline": EMPTY_HEADLINES["known_not_indexed"],
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
                    f"not index ({', '.join(candidates)}), each for a reason its own entry "
                    "states (a careers site whose job-list API requires a request signature, "
                    "or one whose security policy blocks this crawler; we treat both as "
                    "access control). Re-ask with one of them by name for its portal, reason "
                    "and employer opt-in path; dropping the company filter will not find any "
                    "of them."
                )
            else:
                candidates = close
                n = live_employer_count(session)
                hint = (
                    f"This index has no company matching {company!r}. It covers {n} "
                    f"employer{'s' if n != 1 else ''} with live postings, not the whole "
                    "market, so the company is most likely simply not indexed: "
                    + ("retry with one of unknown_companies' suggestions, or drop the company filter."
                       if close else
                       "drop the company filter to search the whole index, or check the employer "
                       "list at github.com/gzchenhao/openhire.")
                )
            return {
                "results": [],
                "matched": 0,
                "status": "unknown_company",
                "headline": EMPTY_HEADLINES["unknown_company"],
                "hint": hint,
                "unknown_companies": [company],
                "suggestions": {company: candidates} if candidates else {},
                "filters_applied": _applied(),
            }

    unknown, suggestions = skill_diagnostics(session, skills, required_skills)


    if unknown:
        # Same rule as the company hint above: point at suggestions only when there are
        # some. "Retry with one of the suggestions" next to `suggestions: {}` sent an agent
        # looking for a list that was not there.
        hint = (
            f"No live posting is tagged {unknown!r}. That tag does not exist in this index, "
            "so this is almost certainly a spelling or naming mismatch rather than a dry "
            "market: "
            + ("retry with one of the suggestions, or drop the tag."
               if any(suggestions.get(t) for t in unknown) else
               "no similar tag exists either, so drop the tag or try the English or "
               "Chinese name of the skill.")
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
    status = "unknown_tag" if unknown else "no_match"
    if not unknown and (location or "").strip():
        cutoff_l = verified_cutoff(session)
        if cutoff_l is not None and not session.scalar(
                select(func.count()).where(live_clause(cutoff_l), _location_clause(location))):
            status = "unknown_location"
            hint = (
                f"No live posting's location matches {location!r} at all, so the place, not the other "
                "filters, emptied this result. Locations match the employer's own text: try the city in "
                "the other language (上海 / Shanghai), a single city rather than a province, or a region "
                "the index knows (China / 全国, Bay Area). 地点对不上：换中文或英文城市名，或写具体城市。"
            )
    if company and not unknown:
        # Every posting we hold for this employer has gone unconfirmed for 30 days: its board
        # most likely moved. Say that instead of "no match", which reads as "not hiring".
        ids = [c.id for c in resolve_company(session, company)]
        cutoff = verified_cutoff(session)
        if ids and cutoff is not None:
            fresh = session.scalar(select(func.count()).where(Job.company_id.in_(ids), live_clause(cutoff))) or 0
            stale = session.scalar(select(func.count()).where(
                Job.company_id.in_(ids), Job.delisted_at.is_(None), Job.verified_at < cutoff)) or 0
            if not fresh and stale:
                status = "not_verified_recently"
                hint = (
                    f"This index holds {stale} postings for {company!r}, but the employer's own system has not "
                    f"returned them for {STALE_AFTER_DAYS} days or more, most likely because its careers board "
                    "moved; they are no longer counted as live. Check the employer's careers page directly, or "
                    "give read_board its current board URL. This says nothing about whether it is hiring."
                )
    return {
        "results": [],
        "matched": 0,
        "status": status,
        "headline": EMPTY_HEADLINES[status],
        "hint": hint,
        "unknown_skills": unknown,
        "suggestions": suggestions,
        "filters_applied": _applied(),
    }


# The first line to show the user when a search returns nothing: which of the different
# "nothing" this is (a tester could not tell "no jobs" from "not ready" from "broken",
# reports/098). The hint below each carries the detail; the headline is fixed wording.
EMPTY_HEADLINES = {
    "index_empty": {"zh": "本机还没有岗位数据，不是没有匹配的岗位。", "en": "There is no job index on this machine yet; this is not a miss."},
    "known_not_indexed": {"zh": "这家公司的岗位在本工具读不到的招聘门户上，去它自己的招聘页看。",
                          "en": "This employer posts on a portal this tool cannot read; use its own careers page."},
    "unknown_company": {"zh": "没有匹配的岗位：索引里没有这家公司。", "en": "No match: this employer is not in the index."},
    "unknown_tag": {"zh": "没有匹配的岗位：条件里有索引认不出的词，换个写法再搜。", "en": "No match: a filter word is unknown to the index; try another spelling."},
    "not_verified_recently": {"zh": "这家公司的岗位已有 30 天以上没在雇主自己的系统里核验到（多半是招聘页搬了），不再算在架；去它的招聘页直接看。",
                              "en": "This employer's postings have not been confirmed by its own system for 30+ days (its board probably moved), so they no longer count as live; check its careers page directly."},
    "unknown_location": {"zh": "没有匹配的岗位：这个地点在索引里一条在架岗位都对不上，换中文或英文城市名、写具体城市再搜。",
                         "en": "No match: no live posting's location matches this place; try the city in the other language or a specific city."},
    "no_match": {"zh": "没有匹配的岗位：条件都认得，只是现在没有在架岗位同时满足，放宽一项再搜。",
                 "en": "No matching postings: every filter is valid, nothing live meets all of them right now; loosen one."},
}


def known_not_indexed_hint(known: list["not_indexed.NotIndexedEmployer"]) -> str:
    """One sentence a seeker can act on: where the postings actually are, why they are
    not here, and that the employer (not the seeker) holds the key to changing that."""
    first = known[0]
    if not first.employer_opt_in:
        # A former employer: nothing to send the seeker to and nobody left to opt in.
        return (
            f"{first.name} is known to us but NOT in this index: {first.reason}. "
            "It no longer has a careers portal, so do not send the user anywhere; tell them "
            "what happened. This is not a typo and dropping the company filter will not "
            "find it; see known_not_indexed[].reason."
        )
    where = (
        f"Its postings are on its own careers portal at {first.careers_url}, so send the "
        "user there directly. An assistant with a browser tool can open that portal and "
        "read the listings as a person would; OpenHire does not index, date or watch what "
        "that page shows."
        if first.careers_url else
        "We have not confirmed its careers portal URL, so do not guess one."
    )
    change = first.employer_opt_in.get("summary") or (
        "authorising the read-only Feishu open-platform scopes "
        + ", ".join(first.employer_opt_in.get("scopes", []))
    )
    return (
        f"{first.name} is known to us but deliberately NOT in this index: {first.reason} "
        f"{where} This is not a typo and dropping the company filter will not find it. "
        f"The employer can change this by {change}; see known_not_indexed[].employer_opt_in."
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


PORTALS_NOTE = (
    "OpenHire does not read, store, date or watch these portals. Each link goes to the "
    "employer's own careers page, the same page a person opens: open it yourself, or let an "
    "assistant with a browser open it. An employer can make its postings readable here; "
    "get_company_info(<name>) says how (employer_opt_in)."
)
PORTALS_NOTE_ZH = (
    "OpenHire 不读、不存、不标日期、不盯这些门户。每个链接都通向雇主自己的招聘页，和人打开的是同一页："
    "自己点开看，或者让带浏览器的助手替你打开。雇主可以让自己的岗位在这里可读，办法见 get_company_info。"
)


def list_portals(sector: str | None = None) -> dict:
    """The link directory for blind spots: employers in this index's sectors whose postings
    sit where OpenHire cannot read them (Feishu Recruitment, BOSS直聘, own pages without a
    readable list), each with its own careers portal and what a browser shows there without
    logging in. Declarative (seed/not_indexed.py): no network, nothing stored."""
    try:
        wanted = not_indexed.parse_sector(sector)
    except ValueError:
        raise OpenHireError(
            "ERR_BAD_SECTOR",
            f"unknown sector {sector!r}; use one of {', '.join(not_indexed.SECTORS)} "
            "(or 自动驾驶 / 具身 / 大模型), or leave it out for all three",
        ) from None
    entries = not_indexed.portals(wanted)
    return {
        "@type": "PortalDirectory",
        "sector": wanted or "all",
        "count": len(entries),
        "portals": [
            {
                "name": e.name,
                "sector": e.sector,
                "sector_zh": not_indexed.SECTOR_NAMES_ZH.get(e.sector),
                "careers_url": e.careers_url,
                "ats": e.ats,
                "visible_without_login": e.visible_without_login,
                "visible_without_login_zh": e.visible_without_login_zh,
                "why_not_indexed": e.reason,
                "why_not_indexed_zh": e.reason_zh,
                "last_checked": e.last_checked,
            }
            for e in entries
        ],
        # Employers the index does read that also list postings on a portal it cannot:
        # their postings there are missing from search results, so the link matters too.
        "also_on_portals_we_cannot_read": [p.as_dict() for p in not_indexed.second_portals(wanted)],
        "note": PORTALS_NOTE,
        "note_zh": PORTALS_NOTE_ZH,
        "also": (
            "Not on this list and not in the index? read_board reads any Greenhouse, Lever, "
            "Ashby, Moka, 北森, Workable, SmartRecruiters, Workday, Rippling or Personio board live; add_employer "
            "keeps one in the user's own index."
        ),
    }


# --- company trust signals (aggregate only) ----------------------------------
def hiring_trend(session: Session, company_id: str) -> dict:
    """What this employer's own system shows over the last 60 days: postings it published in
    the 30 days up to the index's newest verification, the 30 before, and postings taken
    down in the last 30 (reports/114: seekers worried about rescinded offers and "betting on
    a headcount" asked whether a company is growing or shrinking before they sign). Counts
    only, never a forecast: a dip can be a hiring cycle, a burst can be one new office."""
    newest = session.scalar(select(func.max(Job.verified_at)))
    if newest is None:
        return {}
    if isinstance(newest, str):
        newest = dt.datetime.fromisoformat(newest)
    end = _aware(newest)
    mid, start = end - dt.timedelta(days=30), end - dt.timedelta(days=60)

    def _n(*where) -> int:
        return session.scalar(select(func.count()).select_from(Job).where(Job.company_id == company_id, *where)) or 0

    last = _n(Job.posted_at > mid, Job.posted_at <= end)
    prior = _n(Job.posted_at > start, Job.posted_at <= mid)
    down = _n(Job.delisted_at.is_not(None), Job.delisted_at > mid, Job.delisted_at <= end)
    no_date = _n(Job.posted_at.is_(None), Job.first_seen_at > mid)
    zh = (f"截至 {end.date().isoformat()}：近 30 天雇主新发 {last} 条，前 30 天 {prior} 条；"
          f"近 30 天下架 {down} 条。这是雇主系统里的数，不是对公司前景的判断。")
    en = (f"As of {end.date().isoformat()}: {last} postings published in the last 30 days, {prior} in the 30 before; "
          f"{down} taken down in the last 30. Counts from the employer's own system, not a forecast.")
    return {
        "window_end": end.date().isoformat(),
        "new_last_30d": last, "new_prior_30d": prior, "delisted_last_30d": down,
        "first_seen_last_30d_without_employer_date": no_date,
        "in_words": {"zh": zh, "en": en},
    }


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

    cutoff = verified_cutoff(session)
    _live = live_clause(cutoff)
    # Not delisted but not returned by the employer's system for 30 days: no longer counted
    # as live (reports/101); counted here so an employer whose board moved stays visible.
    unverified = session.scalar(
        select(func.count()).where(Job.company_id == company_id, Job.delisted_at.is_(None),
                                   Job.verified_at < cutoff)
    ) if cutoff is not None else 0
    live = select(Job).where(Job.company_id == company_id, _live)
    active_jobs = session.scalar(
        select(func.count()).select_from(live.subquery())
    ) or 0
    ghost_avg = session.scalar(
        select(func.avg(Job.ghost_score)).where(
            Job.company_id == company_id, _live
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
            ).where(Job.company_id == company_id, _live)
        ) if d is not None
    ]
    days_open.sort()
    relisted = session.scalar(
        select(func.count()).where(
            Job.company_id == company_id, _live, Job.relist_count > 0
        )
    ) or 0
    # Same rule as the per-row update_signal (see _touch_is_reported): a vendor with a
    # last-touched field of its own reports it even when no edit has happened yet.
    touch_reported = session.scalar(
        select(func.count()).where(
            Job.company_id == company_id, _live,
            Job.updated_at.is_not(None), Job.posted_at.is_not(None),
            *(() if company.ats_vendor in TOUCH_REPORTING_VENDORS
              else (Job.updated_at != Job.posted_at,)),
        )
    ) or 0
    # Same rule as the per-row `date_signal`: a row whose source reported no posting date
    # is aged from the day this index first saw it. When that is every live row of an
    # employer (Li Auto's first-party mirror carries no date at all), median_days_open is
    # a lower bound on age and not the employer's own timeline, and the caller should
    # know that before reading ghost_score_avg as anything about this employer.
    dates_missing = session.scalar(
        select(func.count()).where(
            Job.company_id == company_id, _live,
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
        # Present only for an employer whose roster is self-reported (ats/self_reported.py):
        # the dates above are the employer's own typing, not an ATS's system clock.
        **({"date_source": "employer_self_reported"} if company.ats_vendor == "self_reported" else {}),
        # Present only when this employer also lists postings on a portal the index cannot
        # read (seed/not_indexed.py SECOND_PORTALS): those postings are not counted above.
        **({"also_posts_on": [p.as_dict() for p in not_indexed.second_portals_for(company.id)]}
           if not_indexed.second_portals_for(company.id) else {}),
        "postings_without_reported_date": int(dates_missing),
        "active_jobs": int(active_jobs),
        # Postings the index still holds for this employer that its own system has not
        # returned for 30 days or more (the board moved, or the crawl keeps failing): not
        # counted in active_jobs and never shown by search. Nonzero is a gap in our reading,
        # not a fact about the employer.
        "unverified_over_30d": int(unverified or 0),
        "hiring_trend": hiring_trend(session, company_id),
        "user_added": bool(getattr(company, "user_added", False)),
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


_WATCH_FILTER_KEYS = (
    "skills", "required_skills", "remote", "role_family", "min_salary", "company", "location",
    "title", "board_url", "seniority", "sector", "entry_level", "posted_within_days",
)
# A board watch (reports/070) reads one employer's public board live on every pull, so the
# only filters that mean anything on it are the ones a live read can apply.
_BOARD_WATCH_KEYS = frozenset({"board_url", "location", "title"})
_SEEN_CAP = 5000


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
        allowed["role_family"] = check_role_family(str(filters["role_family"]))
    if filters.get("title"):
        # Stored as typed; the synonym expansion happens at match time like location.
        allowed["title"] = title_terms(filters["title"])
    if filters.get("seniority"):
        # Validated now, expanded at match time, so a watch on "ic" also keeps a level
        # added to the alias later.
        allowed["seniority"] = check_seniority(filters["seniority"])
    if filters.get("sector"):
        allowed["sector"] = check_sector(filters["sector"])
    if filters.get("entry_level"):
        allowed["entry_level"] = True
    if filters.get("posted_within_days"):
        allowed["posted_within_days"] = check_posted_within_days(filters["posted_within_days"])
    if filters.get("min_salary") is not None:
        allowed["min_salary"] = int(filters["min_salary"])
    if filters.get("location"):
        # Stored as typed; the alias expansion happens at match time, so a watch on 广州
        # registered today also reaches a 天河区 row posted next week.
        allowed["location"] = str(filters["location"]).strip()
    if filters.get("board_url"):
        from .ats.boards import BoardNotSupported, detect_board

        url = str(filters["board_url"]).strip()
        try:
            vendor, tenant = detect_board(url)
        except BoardNotSupported as e:
            raise OpenHireError("ERR_UNSUPPORTED_BOARD", f"[{e.reason}] {e.hint}") from None
        extra = sorted(set(allowed) - _BOARD_WATCH_KEYS)
        if extra:
            raise OpenHireError(
                "ERR_BAD_QUERY",
                f"A board watch reads the employer's board live, which carries no skills, salary or "
                f"role_family: it takes only location and title. Drop {extra}, or register a separate "
                "index watch for them.",
            )
        allowed["board_url"] = url
        allowed["board"] = {"vendor": vendor, "tenant": tenant}
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
    # What the watch matches right now, so the assistant can say "N postings match today,
    # all of them already live" instead of letting the first check_watches pull read as
    # "N new jobs appeared" (a tester, reports/098). A board watch is read live on each
    # pull and has no standing set to count here.
    matching_now = None
    if not clean.get("board_url"):
        matching_now = len(_filter_and_rank(
            session, clean.get("skills"), clean.get("remote"), clean.get("min_salary"), None, 100_000, now,
            required_skills=clean.get("required_skills"), role_family=clean.get("role_family"),
            company_ids=clean.get("company_ids"), location=clean.get("location"),
            title=clean.get("title"), seniority=clean.get("seniority"), sector=clean.get("sector"),
            entry_level=bool(clean.get("entry_level")), posted_within_days=clean.get("posted_within_days"),
        ))
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
    # A short tag is accepted (older clients send "#a3f9") but flagged: four characters
    # collide with strangers, and the collision notice below only fires after it has
    # already happened.
    short = len(fingerprint.strip()) < MIN_FINGERPRINT_LEN
    if clean.get("board_url"):
        next_zh = ("已保存。OpenHire 不会主动推送；下次对我说「检查一下」，我会现读这个招聘页，只列上次之后新出现和已下架的岗位。"
                   "要定时提醒，在助手里另设定时任务，到点调用 check_watches（或用内置提示词 radar_check）。")
        next_en = ("Saved. OpenHire does not push notifications; next time, say \"check my radar\" and the board is read live, "
                   "listing only what appeared or disappeared since the last check. For a scheduled reminder, set a recurring "
                   "task in your assistant that calls check_watches (or uses the built-in radar_check prompt).")
    else:
        n = matching_now or 0
        next_zh = (f"已保存条件，现在匹配 {n} 条，都是已有岗位，不是新发。OpenHire 不会主动推送；下次对我说「检查一下」，"
                   "我只列新出现的岗位（第一次检查会把现在这些先列一遍作为基线）。要定时提醒，在助手里另设定时任务，到点调用 check_watches（或用内置提示词 radar_check）。")
        next_en = (f"Saved. {n} postings match right now, all of them already live, none new. OpenHire does not push notifications; "
                   "next time, say \"check my radar\" and only postings that appeared since are listed (the first check shows the "
                   "current set once, as the baseline). For a scheduled reminder, set a recurring task in your assistant that calls check_watches (or uses the built-in radar_check prompt).")
    return {
        "watch_id": watch_id,
        "status": "active",
        "fingerprint": fingerprint,
        "matching_now": matching_now,
        "what_happens_next": {"zh": next_zh, "en": next_en},
        # Two testers who both picked "#p0ny" saw each other's watches. A collision is
        # not PII (there is none to leak) but it is someone else's intent. Say when the
        # tag was already in use so the client can pick a longer one.
        "existing_watches": int(existing),
        **({"short_fingerprint": True} if short else {}),
        "fingerprint_notice": (
            "Persist this fingerprint yourself — the server cannot recover it. "
            "check_watches needs the identical fingerprint to return your matches."
            + (
                f" This fingerprint is only {len(fingerprint.strip())} characters, which is "
                "short enough to collide with a stranger's: use 12 or more random "
                "characters (e.g. '#a3f9-k2p7-x8q1') and re-register."
                if short else ""
            )
            + (
                f" This fingerprint already had {existing} active watch(es) before this one. If "
                "they are not yours, another client chose the same short tag: use a longer, "
                "random one (12+ characters) and re-register."
                if existing and short else ""
            )
            + (
                f" This fingerprint already has {existing} other active watch(es), most likely "
                "your own from earlier; check_watches returns them all together."
                if existing and not short else ""
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
        if f.get("board_url"):
            entry = _check_board_watch(session, w, f, since, now)
            total_new += len(entry["new_matches"])
            results.append(entry)
            continue
        # Rank the WHOLE standing set, then page it. The old call asked for 20 and then
        # marked the watch notified: everything past row 20 was reported never, and on a
        # broad first pull those 20 were an alphabetical slice, not the best matches.
        ranked_all = _filter_and_rank(
            session, f.get("skills"), f.get("remote"), f.get("min_salary"), since, 100_000, now,
            required_skills=f.get("required_skills"), role_family=f.get("role_family"),
            company_ids=f.get("company_ids"), location=f.get("location"),
            title=f.get("title"), seniority=f.get("seniority"), sector=f.get("sector"),
            entry_level=bool(f.get("entry_level")), posted_within_days=f.get("posted_within_days"),
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
                # The sentence to show the user: a first pull is a baseline of postings that
                # were already live, never "N new jobs appeared" (a tester, reports/098).
                "summary": _watch_summary(since is None, total_matching, len(matches), since),
                "new_matches": matches,
            }
        )
        w.last_notified_at = now
    first = any(r.get("is_first_pull") for r in results)
    return {
        "fingerprint": fingerprint, "watches": len(watches), "new_matches": total_new, "results": results,
        "summary": {
            "zh": (f"{len(watches)} 个雷达。" + ("首次检查：列出的是现在已有的匹配岗位，作为基线，不是新发；以后只报新增。"
                                            if first else (f"新出现 {total_new} 条。" if total_new else "没有新岗位。"))),
            "en": (f"{len(watches)} watch(es). " + ("First check: the postings listed are the ones already live, shown once as the "
                                                  "baseline, not new ones; later checks report only additions."
                                                  if first else (f"{total_new} new posting(s)." if total_new else "Nothing new."))),
        },
    }


def _watch_summary(first_pull: bool, total_matching: int, shown: int, since: dt.datetime | None) -> dict:
    if first_pull:
        return {
            "zh": f"首次检查：当前匹配 {total_matching} 条（列出 {shown} 条），都是已有岗位，不是新发；以后只报新增。",
            "en": (f"First check: {total_matching} postings match today ({shown} listed), all already live, none new; "
                   "later checks report only additions."),
        }
    s = since.date().isoformat() if since else ""
    if total_matching == 0:
        return {"zh": f"自 {s} 以来没有新岗位。", "en": f"Nothing new since {s}."}
    return {"zh": f"自 {s} 以来新出现 {total_matching} 条（列出 {shown} 条）。",
            "en": f"{total_matching} posting(s) appeared since {s} ({shown} listed)."}


def _check_board_watch(session: Session, w: Watch, f: dict, since: dt.datetime | None, now: dt.datetime) -> dict:
    """One pull of a board watch (reports/070): read the board live, report what appeared
    since the last pull and what disappeared, remember what is on it now. A board that does
    not answer leaves the remembered set alone, so nothing is reported closed by accident."""
    seen: dict[str, str] = dict(f.get("_seen") or {})
    base = {"watch_id": w.watch_id, "board_url": f["board_url"], "board": f.get("board"),
            "since": since.isoformat() if since else None, "new_matches": [], "closed_since_last": []}
    try:
        board = read_board(session, url=f["board_url"], location=f.get("location"), title=f.get("title"),
                           limit=100_000, now=now)
    except OpenHireError as e:
        return {**base, "board_error": e.as_dict(), "note": "这次没有读到板，已见清单不变"}
    if not board["ok"]:
        return {**base, "board_error": {"status": board["status"], "error": board["error"]},
                "hint": board.get("hint"), "note": "板没有答复，已见清单不变，不把任何岗位报为已关闭"}
    current = {p["ats_job_id"]: p for p in board["postings"]}
    new = [p for pid, p in current.items() if pid not in seen]
    closed = [{"ats_job_id": pid, "title": title} for pid, title in seen.items() if pid not in current]
    first = since is None and not seen
    remembered = {pid: p["title"] for pid, p in current.items()}
    if len(remembered) > _SEEN_CAP:
        remembered = dict(list(remembered.items())[:_SEEN_CAP])
    w.filters = {**f, "_seen": remembered}
    w.last_notified_at = now
    return {
        **base,
        "is_first_pull": first,
        "total_matching": board["total_matching"],
        "new_matches": new[:MAX_PAGE_SIZE],
        "truncated": len(new) > MAX_PAGE_SIZE,
        "closed_since_last": closed,
        "baseline": ("Everything on this board matching the watch right now; later pulls report only "
                     "postings that appeared or disappeared since.") if first else None,
        "note": BOARD_READ_NOTE,
    }


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

    # Idempotent since 0.8.18 (the maintainer, 2026-10-21, closing the 09-11 tester's
    # item): the same fingerprint authorizing the same posting again gets its first receipt
    # back, not a second record. A client retry or a doubled click cannot inflate the count
    # of authorized applications, which is the only thing an employer may ever pay for.
    existing = session.execute(
        select(Application).where(Application.job_id == job.id, Application.fingerprint == fingerprint,
                                  Application.authorized.is_(True))
        .order_by(Application.created_at).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "delivered_via": existing.delivered_via,
            "receipt_id": existing.receipt_id,
            "resume_transmitted": False,
            "apply_channel": job.apply_channel,
            "already_authorized": True,
            "first_authorized_at": existing.created_at.isoformat() if existing.created_at else None,
            "message": "Already authorized earlier; this is the original receipt, nothing new was recorded. "
                       "Open apply_channel to apply as yourself.",
        }

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
# How many candidates an ambiguous refresh lists. Enough for any real word ("robot" hits
# 11); the hint says when the list is shorter than the match count.
MAX_AMBIGUOUS_CANDIDATES = 25


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
        # The same answer search_jobs and get_company_info give: an employer we know and
        # deliberately do not index is not "unknown". Round 8 got two stories for 小马智行
        # from one server, which is worse than either story alone.
        known = not_indexed.lookup(company)
        if len(known) == 1:
            record = known[0].as_dict()
            # `reason` is this tool's outcome code on every branch; the registry's prose
            # reason keeps its own key so the two never fight over one name.
            record["not_indexed_reason"] = record.pop("reason")
            return {
                "refreshed": False,
                "reason": "known_not_indexed",
                **record,
                "hint": (
                    known_not_indexed_hint(known)
                    + " There is nothing to re-crawl: no ATS of theirs is read by this index."
                ),
            }
        if len(known) > 1:
            return {
                "refreshed": False,
                "reason": "ambiguous_company",
                "candidates": [
                    {"company_id": None, "name": e.name, "indexed": False} for e in known
                ],
                "hint": (
                    f"{company!r} matches {len(known)} employers we know but deliberately do "
                    "not index; none of them can be refreshed. Re-ask with one by name to "
                    "get its portal and reason."
                ),
            }
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
        # The count and the list must agree: "matches 11 employers" over a list of 10 was
        # one more thing a reader had to explain away.
        shown = matched[:MAX_AMBIGUOUS_CANDIDATES]
        return {
            "refreshed": False,
            "reason": "ambiguous_company",
            "candidates": [{"company_id": c.id, "name": c.name} for c in shown],
            "hint": (
                f"{company!r} matches {len(matched)} employers"
                + (f"; candidates lists the first {len(shown)}" if len(shown) < len(matched) else "")
                + ". Re-ask with one company_id; this never refreshes several at once."
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
        "delisted": list(stats.delisted_jobs[:20]),
        "counts_note": ("jobs_updated counts rows whose title or description changed; a row the employer "
                        "re-saved without changing either counts as unchanged, so do not read jobs_updated: 0 "
                        "as \"nobody touched these\" and do not read a recent updated_at as an edit. "
                        "`delisted` names the rows this crawl took down (first 20)."),
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


# --- employer background checklist (reports/065) -------------------------------------
def employer_check(
    session: Session,
    company: str | None = None,
    domain: str | None = None,
    posting_text: str | None = None,
    run_network: bool = True,
    now: dt.datetime | None = None,
    job_id: str | None = None,
    message_text: str | None = None,
) -> dict:
    """Facts about one employer with sources and times. Never a score, never a verdict.

    Resolves `company` the way search does (id or any part of the name, either language);
    an ambiguous name is refused with the candidates rather than guessed. A company we hold
    nothing of but know (the Feishu-hosted ones, 蔚来, a ceased one) comes back with that
    record instead of a bare "not indexed". `domain` is the employer's own site; when it is
    not given it is taken from the employer's careers page only if that page is on the
    employer's domain (a Greenhouse or Moka board says nothing about the employer's domain).
    `job_id` names a posting in this index: the employer is taken from it and, unless
    `posting_text` is given, the red-flag screen runs over the posting as the index holds it
    (title and description), so an assistant can check the role it just found without
    copying text around (reports/068).
    """
    from .verify import build_checklist
    from .verify.checks import normalise_domain, own_domain_from_url

    posting_source = "user" if posting_text else None
    job_company = None
    if job_id:
        job = session.get(Job, job_id)
        if job is None:
            raise OpenHireError("ERR_JOB_NOT_FOUND", f"No job with id '{job_id}'.")
        job_company = session.get(Company, job.company_id)
        company = company or job.company_id
        if posting_text is None:
            posting_text = " ".join(t for t in (job.title, job.description_raw) if t) or None
            posting_source = "index" if posting_text else None
    query = {"company": company, "domain": domain, "job_id": job_id,
             "posting_text_given": bool(posting_text), "posting_text_source": posting_source}
    if not (company or domain) and message_text:
        # A pasted message on its own: scan it, nothing else to look up (reports/108).
        from .verify.employer_check import text_scan_items
        items = text_scan_items(message_text=message_text)
        return {
            "@type": "MessageScan", "checks": items,
            "summary": ("对方的文字里出现了需要停下来的说法，见 checks。" if items[0]["status"] == "not_verified"
                        else "这段文字里没有出现常见的骗局说法。"),
            "next": "Ask for the company's registered full name and run check_employer(company=...) on it; "
                    "the checklist page lists the free official registries.",
            "not_a_verdict": "这是文字里出现了哪些说法的清单，不是对对方的判断。",
            "privacy": "The text was read on this machine and not stored or sent anywhere.",
        }
    if not (company or domain):
        raise OpenHireError("ERR_BAD_QUERY", "Give a company (name or id), a domain, or a pasted message_text.")
    index_facts = None
    known = None
    resolved_domain = normalise_domain(domain) if domain else None
    if company:
        matched = [job_company] if job_company is not None else resolve_company(session, company)
        if len(matched) > 1:
            names = ", ".join(f"{c.id} ({c.name})" for c in matched[:10])
            raise OpenHireError(
                "ERR_AMBIGUOUS_COMPANY",
                f"{company!r} matches {len(matched)} employers: {names}. Re-ask with one id.",
            )
        if len(matched) == 1:
            index_facts = get_company_info(session, matched[0].id, now=now)
            if not resolved_domain:
                resolved_domain = own_domain_from_url(matched[0].careers_url)
        else:
            entries = not_indexed.lookup(company)
            if len(entries) == 1:
                known = entries[0].as_dict()
                if not resolved_domain:
                    resolved_domain = own_domain_from_url(known.get("careers_url"))
    return build_checklist(
        query=query, index_facts=index_facts, known_not_indexed=known,
        domain=resolved_domain, posting_text=posting_text, message_text=message_text, run_network=run_network,
    )


# --- read any employer's board on demand (reports/069) ------------------------------------
# A seeker's market is wider than this index's three sectors. Any employer whose careers
# page sits on a vendor the adapters already read can be read live for the seeker, with
# nothing stored: the same request the weekly crawl makes, once per board per
# BOARD_CACHE_TTL_MINUTES per server process so a chatty client never hammers a vendor.
BOARD_CACHE_TTL_MINUTES = 15
_BOARD_CACHE: dict[tuple[str, str], tuple[dt.datetime, Any]] = {}
BOARD_READ_NOTE = (
    "Read live from the employer's own board and not stored in this index: no skills, no "
    "ghost_score and no relist history, because those need repeated observation. datePosted "
    "and days_open are the board's own where it reports them; date_signal says when it does not."
)
BOARD_READ_PRIVACY = (
    "This read sent only the board's tenant to the vendor's public endpoint, the same request "
    "the weekly crawl makes. Nothing about you was sent, and nothing read was stored."
)


def _fetch_board(vendor: str, tenant: str):
    """One live read of a board. The network call lives in pipeline.crawler, never in this
    module (tests/test_three_nos.py: nothing in the apply path can call out)."""
    from .pipeline.crawler import fetch_board

    return fetch_board(vendor, tenant)


# Where the role itself starts in a description that opens with the company's boilerplate
# ("About Anthropic ... About the role"): the persona test of 2026-10-30 got 400 characters
# of company introduction and none of the job. The excerpt starts at the first of these.
_ROLE_START = re.compile(
    r"about (the|this) (role|position|job|team)|the role\b|the opportunity|what you('|’)ll do|what you will do"
    r"|responsibilities|your role|in this role|job description|职位描述|岗位职责|工作职责|职位职责|岗位描述|工作内容",
    re.I,
)
EXCERPT_CHARS = 400
FULL_DESCRIPTION_CHARS = 20000


def role_excerpt(text: str | None, n: int = EXCERPT_CHARS) -> str:
    """The first `n` characters of the description from where the role starts, or from the
    top when no marker is found or what follows it is too short to be the role."""
    text = (text or "").strip()
    m = _ROLE_START.search(text)
    start = m.start() if m and len(text) - m.start() >= 200 else 0
    return text[start:start + n]


def _board_posting(rec, now: dt.datetime, full: bool = False) -> dict:
    posted = _aware(rec.posted_at) if rec.posted_at else None
    updated = _aware(rec.updated_at) if rec.updated_at else None
    scope, regions = classify_remote(rec.remote_hint, rec.location)
    out = {
        "ats_job_id": rec.ats_job_id,
        "title": rec.title,
        "seniority": seniority_from_title(rec.title),
        "requirements": requirements_from_text(rec.title, rec.description_raw),
        "location": rec.location,
        "remote_policy": rec.remote_hint or "unknown",
        "remote_scope": scope,
        "eligible_regions": regions,
        "datePosted": posted.date().isoformat() if posted else None,
        "days_open": (now - posted).days if posted else None,
        "date_signal": "ats_reported" if posted else "not_reported_by_ats",
        "dates_in_words": (
            dates_in_words(posted.date(), (now - posted).days, "board_live", None)
            if posted else
            {"zh": "这家的招聘页没有标发布日期；本次是现读，不是索引记录，所以也没有首次发现日期。",
             "en": "The employer's board shows no posting date; this was a live read, not an index record, so there is no first-seen date either."}
        ),
        "updated_at": updated.isoformat() if updated else None,
        "days_since_update": (now - updated).days if updated else None,
        "apply_channel": rec.apply_channel,
        "description_excerpt": role_excerpt(rec.description_raw),
        "description_chars": len(rec.description_raw or ""),
    }
    if full:
        out["description"] = (rec.description_raw or "")[:FULL_DESCRIPTION_CHARS]
    if rec.salary_min or rec.salary_max:
        out.update(salary_min=rec.salary_min, salary_max=rec.salary_max,
                   salary_currency=rec.salary_currency, salary_period=rec.salary_period)
    return out



# --- the user's own employers (0.8.13) ----------------------------------------------------
# The public index is a curated seed list (three sectors, one roster for everyone). A real
# search is wider than that: the employers one person targets are theirs to pick. Any
# board a vendor adapter can read goes into THIS machine's index on request, with the same
# dates, ghost_score, watches and refresh as a seeded employer; the row is flagged
# user_added so it never enters a published snapshot and survives every weekly refresh
# (pipeline/snapshot.carry_over_user_state). Nothing about the user leaves the machine:
# the vendor sees the same tenant read the weekly crawl would make.
PUBLIC_INDEX_ISSUE_URL = "https://github.com/gzchenhao/openhire/issues/new"
USER_EMPLOYER_NOTE = (
    "This employer is in the index on this machine only (user_added): search_jobs, watch_intent, "
    "refresh_index and ghost_score cover it like any seeded employer; the weekly refresh keeps it; "
    "it is never part of the public snapshot. remove_employer takes it out again."
)


def suggest_public_index_url(vendor: str, tenant: str, careers_url: str | None) -> str:
    """A prefilled GitHub issue the user can open to propose the employer for the public
    index. A link, not a request: nothing is sent unless the user opens it."""
    from urllib.parse import quote

    title = f"Add employer to the public index: {tenant} ({vendor})"
    body = (
        f"Employer board: {careers_url or ''}\n"
        f"Vendor / tenant: {vendor} / {tenant}\n"
        "Sector (AI infra / autonomous driving / embodied AI / other): \n"
        "Why it belongs in the public index: \n"
    )
    return f"{PUBLIC_INDEX_ISSUE_URL}?title={quote(title)}&body={quote(body)}"


def _default_employer_name(vendor: str, tenant: str) -> str:
    head = tenant.split("/", 1)[0]
    if vendor == "workday":
        head = head.split(".", 1)[0]
    return head


def _user_company_id(session: Session, vendor: str, tenant: str) -> str:
    base = re.sub(r"[^a-z0-9._-]+", "-", _default_employer_name(vendor, tenant).lower()).strip("-.") or vendor
    if session.get(Company, base) is None:
        return base
    alt = f"{vendor}-{base}"
    n = 2
    while session.get(Company, alt) is not None:
        alt = f"{vendor}-{base}-{n}"
        n += 1
    return alt


def add_employer(
    session: Session,
    url: str,
    name: str | None = None,
    now: dt.datetime | None = None,
    fetch=None,
) -> dict:
    """Put one employer's board into this machine's index and crawl it once, now."""
    from .ats import get_client
    from .ats.boards import BoardNotSupported, detect_board
    from .pipeline.extract import get_extractor
    from .pipeline.ingest import IngestStats, ingest_company

    now = _now(now)
    try:
        vendor, tenant = detect_board(url)
    except BoardNotSupported as e:
        raise OpenHireError("ERR_UNSUPPORTED_BOARD", f"[{e.reason}] {e.hint}") from None

    existing = session.execute(
        select(Company).where(Company.ats_vendor == vendor, Company.ats_tenant == tenant)
    ).scalars().first()
    if existing is not None:
        return {
            "added": False,
            "reason": "already_in_index",
            "company_id": existing.id,
            "company": existing.name,
            "user_added": bool(getattr(existing, "user_added", False)),
            "hint": (f"{existing.name} is already in this index as {existing.id}"
                     + (" (added by the user)." if getattr(existing, "user_added", False) else " (part of the public index).")
                     + f" search_jobs(company=\"{existing.id}\") has its postings; refresh_index re-crawls it."),
        }

    result = (fetch or _fetch_board)(vendor, tenant)
    if not result.ok:
        raise OpenHireError(
            "ERR_BOARD_UNREADABLE",
            f"{vendor}:{tenant} did not answer (HTTP {result.status}, {result.error or 'no detail'}); "
            "nothing about the employer follows from that, and nothing was added. Check the URL on the "
            "employer's careers page and try again later.",
        )

    client = get_client(vendor)
    company_id = _user_company_id(session, vendor, tenant)
    display = (name or "").strip() or _default_employer_name(vendor, tenant)
    company = Company(
        id=company_id, name=display, ats_vendor=vendor, ats_tenant=tenant,
        careers_url=client.careers_url(tenant), verified=False, user_added=True,
    )
    session.add(company)
    session.flush()
    stats = IngestStats()
    ingest_company(session, company, result, get_extractor(), stats, now=now)
    session.flush()
    return {
        "added": True,
        "company_id": company_id,
        "company": display,
        "vendor": vendor,
        "tenant": tenant,
        "careers_url": company.careers_url,
        "count_on_board": result.count,
        "jobs_indexed": stats.jobs_new,
        "user_added": True,
        "stored": "this machine's index only",
        "hint": (f"Added. search_jobs(company=\"{company_id}\") lists its postings with dates and days_open; "
                 f"watch_intent(filters={{\"company\": \"{company_id}\"}}) watches it; refresh_index re-crawls it. "
                 "Pass name= to give it a proper display name."),
        "note": USER_EMPLOYER_NOTE,
        "suggest_for_public_index": suggest_public_index_url(vendor, tenant, company.careers_url),
    }


def remove_employer(session: Session, company: str) -> dict:
    """Take a user-added employer (and its postings) out of this machine's index."""
    matched = resolve_company(session, company)
    if not matched:
        raise OpenHireError("ERR_COMPANY_NOT_FOUND", f"No employer in this index matches {company!r}.")
    if len(matched) > 1:
        names = ", ".join(f"{c.id} ({c.name})" for c in matched[:10])
        raise OpenHireError("ERR_AMBIGUOUS_COMPANY", f"{company!r} matches {len(matched)} employers: {names}. Re-ask with one id.")
    target = matched[0]
    if not getattr(target, "user_added", False):
        raise OpenHireError(
            "ERR_NOT_USER_ADDED",
            f"{target.name} ({target.id}) is part of the public index, not an employer the user added; "
            "only user-added employers can be removed here.",
        )
    n = session.execute(delete(Job).where(Job.company_id == target.id)).rowcount or 0
    session.delete(target)
    session.flush()
    return {"removed": True, "company_id": target.id, "company": target.name, "jobs_removed": int(n)}

def read_board(
    session: Session,
    url: str,
    location: str | None = None,
    title: str | list[str] | None = None,
    limit: int = 30,
    offset: int = 0,
    now: dt.datetime | None = None,
    fetch=None,
    cache_ttl_minutes: int = BOARD_CACHE_TTL_MINUTES,
    ats_job_id: str | None = None,
) -> dict:
    """Read one employer's public board live, whether or not the employer is indexed.

    With `ats_job_id`, only that posting comes back, with its whole description
    (`description`, up to FULL_DESCRIPTION_CHARS) for the user to read or summarise.

    `url` is the careers URL as the seeker pasted it; `ats.boards.detect_board` turns it
    into the (vendor, tenant) the adapter takes, or refuses it with the reason (a Feishu
    portal, Workday, a job site). The board's postings come back with the same honest date
    semantics as the index (the board's own date or `not_reported_by_ats`) and a direct
    apply link on the employer's own tenant; nothing is written to the index. A board that
    does not answer is reported as such, never as a fact about the employer.
    """
    from .ats import get_client
    from .ats.boards import BoardNotSupported, detect_board

    now = _now(now)
    try:
        vendor, tenant = detect_board(url)
    except BoardNotSupported as e:
        raise OpenHireError("ERR_UNSUPPORTED_BOARD", f"[{e.reason}] {e.hint}") from None
    if limit < 1:
        raise OpenHireError("ERR_BAD_PAGE", "limit must be at least 1.")
    offset = max(0, int(offset or 0))

    key = (vendor, tenant)
    cached = _BOARD_CACHE.get(key)
    if cached and now - cached[0] < dt.timedelta(minutes=cache_ttl_minutes):
        fetched_at, result = cached
        from_cache = True
    else:
        result = (fetch or _fetch_board)(vendor, tenant)
        fetched_at, from_cache = now, False
        if result.ok:
            _BOARD_CACHE[key] = (fetched_at, result)

    company = session.execute(
        select(Company).where(Company.ats_vendor == vendor, Company.ats_tenant == tenant)
    ).scalars().first()
    out = {
        "@type": "BoardRead",
        "vendor": vendor,
        "tenant": tenant,
        "careers_url": get_client(vendor).careers_url(tenant),
        "source": "ats_public_api",
        "stored": False,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "from_cache": from_cache,
        "ok": bool(result.ok),
        "status": result.status,
        "error": result.error,
        "in_index": {"company_id": company.id, "name": company.name} if company else None,
        "count_on_board": result.count if result.ok else 0,
        "total_matching": 0,
        "postings": [],
        "truncated": False,
        "note": BOARD_READ_NOTE,
        "privacy": BOARD_READ_PRIVACY,
    }
    if company:
        out["hint"] = (f"{company.name} is in this index as {company.id}: search_jobs(company=\"{company.id}\") "
                       "carries skills, ghost_score, relist history and watches for it; this live read does not.")
    else:
        out["add_to_my_index"] = (f"add_employer(url=\"{url}\") puts this board in the user's own index on this "
                                  "machine: then search_jobs, watch_intent, refresh_index and ghost_score cover it.")
        out["suggest_for_public_index"] = suggest_public_index_url(vendor, tenant, out["careers_url"])
    if not result.ok:
        out["hint"] = (f"The board did not answer (HTTP {result.status}, {result.error or 'no detail'}); "
                       "nothing about the employer follows from that. Open the careers page yourself.")
        return out

    terms = title_terms(title)
    aliases = [a.casefold() for a in location_aliases(location)] if location else []
    rows = []
    want = str(ats_job_id).strip() if ats_job_id else None
    for rec in result.records:
        if want is not None and str(rec.ats_job_id) != want:
            continue
        if aliases and not any(a in (rec.location or "").casefold() for a in aliases):
            continue
        if terms and not title_matches(rec.title, terms):
            continue
        rows.append(rec)
    rows.sort(key=lambda r: (r.posted_at is None, -_aware(r.posted_at).timestamp() if r.posted_at else 0))
    page = rows[offset:offset + limit]
    out["total_matching"] = len(rows)
    out["truncated"] = offset + len(page) < len(rows)
    out["postings"] = [_board_posting(rec, now, full=want is not None) for rec in page]
    if want is not None and not rows:
        out["hint"] = (f"No posting with ats_job_id {want!r} is on this board now: it may have closed. "
                       "Read the board without ats_job_id to see what is open.")
    return out


# --- application tracker: an answer to "read, no reply" (reports/112) -----------
# Zhihu's most-asked young-seeker question is some form of "投了一堆简历都是已读不回，是真的在
# 招人吗?". Whether the employer will reply is not ours to know; whether the posting is still
# on the employer's own system is, and it is the half that tells a seeker when to stop
# waiting. A tracked posting is an Application row with authorized=False and
# delivered_via=TRACKED_VIA: the user applied somewhere themselves and asks us to follow
# the posting, which is not an authorization and is never counted as one.
TRACKED_VIA = "user_tracked"
MAX_TRACKED = 200


def check_applications(
    session: Session,
    fingerprint: str,
    add_job_ids: list[str] | None = None,
    remove_job_ids: list[str] | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """The status of every posting this fingerprint applied to or asked to follow, read
    from the employer's own system: still live, closed (delisted) since, or not returned by
    the employer's system for 30 days. Facts only: a live posting may still never answer,
    and a closed one may have been filled or withdrawn; we cannot see which."""
    now = _now(now)
    _assert_anonymous(fingerprint)
    added, unknown, removed = [], [], []
    for jid in [str(j).strip() for j in (add_job_ids or []) if str(j).strip()]:
        _assert_anonymous(jid)
        if session.get(Job, jid) is None:
            unknown.append(jid)
            continue
        exists = session.execute(
            select(Application.receipt_id).where(Application.fingerprint == fingerprint, Application.job_id == jid)
        ).first()
        if exists:
            continue
        n = session.scalar(select(func.count()).select_from(Application).where(Application.fingerprint == fingerprint)) or 0
        if n >= MAX_TRACKED:
            raise OpenHireError("ERR_TOO_MANY", f"A fingerprint follows at most {MAX_TRACKED} postings; remove some first.")
        session.add(Application(receipt_id=_new_id(session, Application, "receipt_id", "t_"), job_id=jid,
                                fingerprint=fingerprint, authorized=False, delivered_via=TRACKED_VIA, created_at=now))
        session.flush()
        added.append(jid)
    for jid in [str(j).strip() for j in (remove_job_ids or []) if str(j).strip()]:
        rows = session.execute(select(Application).where(
            Application.fingerprint == fingerprint, Application.job_id == jid,
            Application.delivered_via == TRACKED_VIA)).scalars().all()
        for r in rows:
            session.delete(r)
        if rows:
            removed.append(jid)
    session.flush()

    cutoff = verified_cutoff(session)
    apps = session.execute(
        select(Application).where(Application.fingerprint == fingerprint).order_by(Application.created_at)
    ).scalars().all()
    seen: set[str] = set()
    items, counts = [], {"open": 0, "closed": 0, "not_verified_recently": 0}
    for a in apps:
        if a.job_id in seen:
            continue
        seen.add(a.job_id)
        job = session.get(Job, a.job_id)
        if job is None:
            continue
        company = session.get(Company, job.company_id)
        since = _aware(a.created_at)
        days_since = (now - since).days if since else None
        posted = _aware(job.posted_at) if job.posted_at else None
        updated = _aware(job.updated_at) if job.updated_at else None
        if job.delisted_at is not None:
            status = "closed"
            closed = _aware(job.delisted_at).date().isoformat()
            zh = f"已从雇主系统下架（索引在 {closed} 发现），不用再等这一个了。"
            en = f"Taken off the employer's system (seen by the index on {closed}); no need to keep waiting on this one."
        elif cutoff is not None and _aware(job.verified_at) < cutoff:
            status = "not_verified_recently"
            zh = "雇主系统 30 天内没有再返回这个岗位，多半已不在招，但我们没法确认。"
            en = "The employer's system has not returned this posting for 30 days; it is probably no longer open, but we cannot confirm it."
        else:
            status = "open"
            age = f"已在架 {(now - posted).days} 天" if posted else "雇主没标发布日期"
            touched = "，你记下之后雇主改动过它" if (updated and since and updated > since) else ""
            zh = f"还在雇主系统上（{age}{touched}）。还在架不代表会回复，只说明岗位没撤。"
            en = (f"Still on the employer's system ({f'open {(now - posted).days} days' if posted else 'no posting date from the employer'}"
                  f"{'; the employer edited it after you noted it' if touched else ''}). Live does not mean a reply is coming, only that the posting was not withdrawn.")
        counts[status] += 1
        items.append({
            "job_id": job.id, "title": job.title,
            "company": company.name if company else job.company_id,
            "location": job.location,
            "kind": "authorized" if a.authorized else "tracked",
            "noted_at": since.date().isoformat() if since else None,
            "days_since_noted": days_since,
            "status": status,
            "status_in_words": {"zh": zh, "en": en},
            "apply_channel": job.apply_channel,
        })
    order = {"closed": 0, "not_verified_recently": 1, "open": 2}
    items.sort(key=lambda r: (order[r["status"]], -(r["days_since_noted"] or 0)))
    total = len(items)
    summary = {
        "zh": (f"你记下的 {total} 个岗位里：{counts['closed']} 个已从雇主系统下架，{counts['not_verified_recently']} 个 "
               f"30 天没再出现，{counts['open']} 个还在架。下架和长期不出现的，不用再等回复了。") if total else
              "还没有记下任何岗位。说一句「我投了这几个」，把 job_id 传给 add_job_ids 就能开始跟。",
        "en": (f"Of the {total} postings you noted: {counts['closed']} closed on the employer's system, "
               f"{counts['not_verified_recently']} not seen for 30 days, {counts['open']} still live. "
               "Stop waiting on the closed and long-unseen ones.") if total else
              "Nothing noted yet. Pass the job_ids you applied to as add_job_ids to start following them.",
    }
    return {
        "fingerprint": fingerprint, "summary": summary, "counts": {**counts, "total": total},
        "applications": items, "added": added, "removed": removed, "unknown_job_ids": unknown,
        "note": ("Only postings in this index can be followed (job_id from search_jobs). Whether the employer "
                 "will reply is not something any index can see; this answers whether the posting is still there."),
    }


# --- salary benchmark: what employers themselves publish (reports/118) ----------
# Pay ranges employers put on their own postings (US pay-transparency law makes most US
# ones carry one). Low and high ends are reported separately: Chinese ranges are often
# wide (19% of stated CNY ranges span 2x or more on the 2026-10-26 index), and a midpoint
# of 15K to 40K says less than "the lows sit around X, the highs around Y". Grouped by
# level as the title names it plus the years the posting asks for, never by company grade
# (P7, T9), which no two employers spell alike. A group under MIN_PEERS rows gets a count
# and no quantiles.
MIN_PEERS = 20
WIDE_RANGE_RATIO = 2.0


def _quantiles(values: list[float]) -> dict:
    v = sorted(values)
    n = len(v)

    def q(p: float) -> int:
        i = (n - 1) * p
        lo, hi = int(i), min(int(i) + 1, n - 1)
        return int(round(v[lo] + (v[hi] - v[lo]) * (i - lo)))
    return {"p25": q(0.25), "median": q(0.5), "p75": q(0.75)}


def _salaried_rows(session: Session) -> list[tuple]:
    """(company_id, title, role_family, currency, annual_low, annual_high, description) for
    every live row whose stated pay we would publish."""
    out = []
    stmt = select(Job.company_id, Job.title, Job.role_family, Job.salary_currency, Job.salary_min,
                  Job.salary_max, Job.salary_period, Job.description_raw).where(
        live_clause(verified_cutoff(session)),
        (Job.salary_min.isnot(None)) | (Job.salary_max.isnot(None)),
    )
    for cid, title, rf, cur, lo, hi, period, desc in session.execute(stmt):
        lo, hi, _ = usable_salary(lo, hi, period)
        if lo is None and hi is None or not cur:
            continue
        out.append((cid, title or "", (rf or classify_role_family_heuristic(title or "") or "").lower() or None,
                    cur.upper(), annualise(lo, period), annualise(hi, period), desc))
    return out


def salary_benchmark(
    session: Session,
    currency: str,
    role_family: str | None = None,
    seniority: list[str] | None = None,
    sector: str | None = None,
    location: str | None = None,
    title: str | list[str] | None = None,
    years_min: int | None = None,
    years_max: int | None = None,
) -> dict:
    from .seed.sectors import sector_of
    cur = (currency or "").strip().upper()
    if not cur:
        raise OpenHireError("ERR_BAD_QUERY", "currency is required (USD, CNY, GBP, EUR, CAD, ...): ranges in different currencies are never mixed.")
    rf = check_role_family(role_family)
    levels = expand_seniority(check_seniority(seniority))
    sec = check_sector(sector)
    terms = title_terms(title)
    loc_ids = None
    if location:
        loc_ids = set(session.execute(select(Job.id).where(_location_clause(location), live_clause(verified_cutoff(session)))).scalars())
    lows, highs, companies, wide, n = [], [], set(), 0, 0
    rows = _salaried_rows(session) if loc_ids is None else None
    if rows is None:
        rows = []
        stmt = select(Job.company_id, Job.title, Job.role_family, Job.salary_currency, Job.salary_min,
                      Job.salary_max, Job.salary_period, Job.description_raw).where(Job.id.in_(loc_ids))
        for cid, t, r, c, lo, hi, period, desc in session.execute(stmt):
            lo, hi, _ = usable_salary(lo, hi, period)
            if (lo is None and hi is None) or not c:
                continue
            rows.append((cid, t or "", (r or classify_role_family_heuristic(t or "") or "").lower() or None,
                         c.upper(), annualise(lo, period), annualise(hi, period), desc))
    for cid, t, r, c, lo, hi, desc in rows:
        if c != cur or (rf and r != rf) or (sec and sector_of(cid) != sec):
            continue
        if levels is not None and seniority_from_title(t) not in levels:
            continue
        if terms and not title_matches(t, terms):
            continue
        if years_min is not None or years_max is not None:
            y = requirements_from_text(t, desc)["min_years"]
            if y is None or (years_min is not None and y < years_min) or (years_max is not None and y > years_max):
                continue
        n += 1
        companies.add(cid)
        if lo is not None:
            lows.append(lo)
        if hi is not None:
            highs.append(hi)
        if lo and hi and hi >= WIDE_RANGE_RATIO * lo:
            wide += 1
    applied = {k: v for k, v in {"currency": cur, "role_family": rf, "seniority": seniority, "sector": sec,
                                 "location": location, "title": terms or None, "years_min": years_min,
                                 "years_max": years_max}.items() if v not in (None, [], "")}
    out = {
        "source": "employer_published_ranges",
        "filters_applied": applied,
        "postings": n, "employers": len(companies), "wide_ranges": wide,
        "annual_low": None, "annual_high": None,
    }
    if n >= MIN_PEERS:
        out["annual_low"] = _quantiles(lows) if len(lows) >= MIN_PEERS else None
        out["annual_high"] = _quantiles(highs) if len(highs) >= MIN_PEERS else None
    if out["annual_low"] and out["annual_high"]:
        zh = (f"{n} 条雇主自己标了薪资的在架岗位（{len(companies)} 家公司）：年薪下限中位数 {out['annual_low']['median']:,} {cur}，"
              f"上限中位数 {out['annual_high']['median']:,} {cur}；其中 {wide} 条范围宽到 2 倍以上。数字来自雇主公开标注，不是成交价。")
        en = (f"{n} live postings with employer-published pay ({len(companies)} employers): median low end {out['annual_low']['median']:,} {cur}, "
              f"median high end {out['annual_high']['median']:,} {cur}; {wide} ranges span 2x or more. Published ranges, not offers.")
    else:
        zh = (f"只有 {n} 条雇主自己标了薪资的在架岗位符合这些条件，少于 {MIN_PEERS} 条，不给分位数。中国岗位大多不标薪资，放宽条件或换币种再看。")
        en = (f"Only {n} live postings with employer-published pay match; under {MIN_PEERS}, so no quantiles. Most Chinese postings publish no pay; widen the filters.")
    out["in_words"] = {"zh": zh, "en": en}
    out["note"] = ("Annualised from monthly where the posting says so (x12; a 13th or 14th month is not added). Grouped by the level the title names and the years "
                   "the posting asks for, not by company grade. Most postings in China state no pay at all.")
    return out
