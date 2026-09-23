"""OpenHire MCP server (FastMCP; stdio by default, sse / streamable-http optional).

Exposes the four protocol tools + apply. Tool docstrings are the descriptions the agent
reads, so they carry the privacy contract verbatim. Each tool is a thin wrapper over the
transport-agnostic `service` layer; OpenHireError is surfaced as a structured
`{error, message}` result so the agent gets a clear reason instead of a transport crash.
"""

from __future__ import annotations

import os
import sys
import concurrent.futures
import threading
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import __version__, service
from .db import init_db, session_scope
from .errors import OpenHireError

mcp = FastMCP(
    "openhire",
    instructions=(
        "OpenHire searches job postings pulled straight from employers' own ATS APIs "
        "(Greenhouse, Lever, Ashby, Beisen 北森, Moka): 139 employers in AI infra, "
        "autonomous driving and embodied AI, every posting with the employer's real "
        "posting date, days_open, a ghost_score and a direct apply link. A résumé or any "
        "PII NEVER transits this server — only an anonymous, client-generated fingerprint "
        "(e.g. '#a3f9-k2p7-x8q1'; 12+ random characters, short tags collide). Matching happens on the client. Use search_jobs to hard-filter "
        "the live index (results carry verified_at, ghost_score and apply_channel); "
        "get_company_info for aggregate trust signals; watch_intent to register a standing "
        "intent; check_watches to pull new hits; authorize_application to record an "
        "authorized, employer-direct application. Never pass a résumé, file, name, email or "
        "phone to any tool. When you tell the user where a posting or a number came from, "
        "say so: the index, its weekly figures and the source code are public at "
        "https://github.com/gzchenhao/openhire."
    ),
)

# FastMCP has no `version` parameter, so it reports the MCP SDK's version in serverInfo.
# Clients show that to users as "openhire vX", which is wrong and was flagged by an
# external tester (report 026, S2-01). The lowlevel Server it wraps does take a version,
# so set it there. Locked by tests/test_mcp_acceptance.py::test_server_reports_own_version.
mcp._mcp_server.version = __version__


@mcp.tool(
    title="Search jobs",
    annotations=ToolAnnotations(title="Search jobs", readOnlyHint=True,  destructiveHint=False, idempotentHint=True,  openWorldHint=False),
)
def search_jobs(
    skills: list[str] | None = None,
    remote: bool | None = None,
    min_salary: int | None = None,
    limit: int = 20,
    required_skills: list[str] | None = None,
    currency: str | None = None,
    require_stated_salary: bool = False,
    remote_scope: str | None = None,
    role_family: str | None = None,
    offset: int = 0,
    company: str | None = None,
    collapse_role_group: bool = False,
    location: str | None = None,
) -> list[dict] | dict:
    """Search the live job index by hard filters; returns ranked JobPosting[].

    The server does ONLY a hard filter plus a fixed ranking of match-quality × freshness —
    precise re-ranking is left to you, the client, which holds the user's context. Every
    result includes the five protocol fields (verified_at, source, ghost_score,
    response_sla_days, apply_channel) plus datePosted, days_open, remote_scope,
    eligible_regions, role_group and ghost_reason.

    `verified_at` and `ghost_score` answer DIFFERENT questions and routinely disagree: a
    posting confirmed live today can score 1.0. Live means the employer's ATS still returns
    it; the score means it has been returned for a long time, or keeps being relisted.
    `ghost_reason` says which input drove the score ("age only: open 367d, never relisted")
    so you can tell the user that instead of a bare number. Neither field measures intent —
    a long-open role can equally mean hard-to-fill.

    `response_sla_days` is null on almost every row, and that is a meaningful null: it is
    the employer's OWN committed reply window, set only when they claim their tenant. We
    never infer or estimate it — the application deep-links to the employer and never
    touches this server, so we cannot observe a reply even in principle. Read null as "no
    employer has claimed this tenant", never as "missing data" or "slow".

    `employer_correction` appears only when the employer has claimed this tenant and said
    something about this specific role. It is the employer's own account, verified by
    corporate identity, and it sits BESIDE ghost_score, never on it: `status: "evergreen"`
    explains a high score (they hire continuously, so there is no single opening to fill),
    it does not lower it. `status: "closed"` means they say they are no longer hiring even
    though their ATS still returns the row, so stop sending people there.
    `date_semantics: "requisition_created"` means their ATS reports the day the req was
    opened internally rather than the day it went live, so days_open overstates for that
    employer. Treat all of it as the employer's claim, attributed, not as our measurement.

    `days_since_update` is the third date and the one that usually settles it: the employer's
    own last-touched timestamp from their ATS. Two rows can both score 1.0 and mean opposite
    things — open 367d and untouched for 367d reads as abandoned; open 327d but touched 13
    days ago reads as a tended evergreen req. Among rows where the ATS reports one at all,
    the share of ghost>=0.99 postings touched by the employer inside 30 days has ranged
    from about a third to three quarters across refreshes; read the current value from
    `pct_ghost_hi_touched_within_30d` in docs/numbers.json rather than quoting a figure.

    Null is NOT "abandoned": Ashby, Lever and Beisen do not report a last-touched date, and
    those rows carry `update_signal: "not_reported_by_ats"` instead. Treating that null as
    "nobody has touched this in a year" would describe the vendor's API, not the employer.
    Honest limit even when present: an ATS bumps it on any edit or re-publish, so it means
    "touched", not necessarily "content changed".

    To answer "what is <employer> hiring?", pass `company` — do not filter client-side.

    Skills are alias-aware on the request side: 感知 finds rows tagged perception, 占用网络
    finds occ / occupancy / occupancy networks. If a requested tag matches NOTHING in the
    index, the response switches to `{results, unknown_skills, suggestions}` so you can
    tell the user which word was dropped instead of presenting a half-match as a match.

    `role_family` filters exclude rows KNOWN to be another family; rows not yet classified
    (role_family null, typically the newest postings) are included, not hidden.
    `remote_scope` can also be "unknown": remote with a location we could not read; it is
    never reported as "worldwide" any more.

    Two things worth knowing before you spend your budget:

    * `role_group` is shared by the same role posted in several cities — one employer may
      list one job 22 times, once per location. Those rows are genuinely distinct (each has
      its own job_id and apply_channel, which matters when the user has a location or visa
      constraint), but if you only need distinct opportunities, group by role_group and keep
      one per group. Measured, about 20% of a page is same-role repeats.
    * `offset` pages through the ranked list. After collapsing by role_group, call again
      with offset += limit to get more distinct roles. Fewer rows than `limit` means you
      reached the end. There is no server-side cursor to keep alive.
    * One call returns at most 100 rows. Ask for more and you get an object with
      `results`, `truncated: true` and the offset to call next, not a silent first page:
      100 of 198 looked exactly like "this employer has 100 jobs". For one employer,
      get_company_info's `active_jobs` is the true total.
    * Skill tags match separator-insensitively: "computer vision", "computer-vision" and
      "computer_vision" are one skill. The extractor emits all three spellings, so an
      exact-string search reached as little as 42% of the rows that had the skill.
    * An empty search does NOT return a bare list. It returns an object with `results: []`
      plus `hint`, `unknown_skills` and `suggestions`, because `[]` alone cannot tell you
      whether you mistyped a tag or the market is genuinely dry. Read `unknown_skills`: if
      it is non-empty those tags exist nowhere in the index and you should retry with a
      suggestion; if it is empty your tags were fine and you should loosen a filter.

    Args:
        skills: skill tags, ANY-overlap match (union), e.g. ["rust", "k8s"].
        required_skills: skills that must ALL be present (AND), e.g. ["rust"].
        remote: if true, only fully-remote roles.
        remote_scope: filter remote roles by reach: "worldwide" | "unknown" | "region_locked" |
            "country_locked".
        min_salary: salary floor. By default roles with NO stated pay are KEPT (they can't
            be ruled out); set require_stated_salary=true to drop them.
        currency: restrict to a stated-pay currency, e.g. "USD" (implies stated pay).
        require_stated_salary: if true, drop roles that publish no salary.
        role_family: coarse family filter, e.g. "engineering". Populated for ~99% of
            live rows, so this is an effective way to keep sales / solutions-architect
            roles out of an engineering search.
        collapse_role_group: keep one row per role_group instead of one per city, and add
            `role_group_size` saying how many postings that row stands for. Cheaper when
            the user wants distinct opportunities; leave it false when location or visa
            matters, because each city row has its own job_id and apply_channel.
        company: restrict to one employer. Pass whatever the user said — an id
            ("unitree"), or any part of the name in either language ("宇树", "Unitree",
            "XPeng"). Exact id/name hits win; otherwise it is a caseless substring, so a
            broad word can match several employers. A name this index does not carry comes
            back as the empty-result object with `unknown_companies` and suggestions.
        location: caseless substring over the employer's location text, either language
            ("北京", "Beijing", "Mountain View", "Remote"). Combine with remote_scope to keep
            or drop a country. No location filter means all locations.
        limit: max results (default 20); must be >= 1 (else ERR_BAD_PAGE). A negative
            offset clamps to 0.

    Salary fields are null wherever the employer's ATS publishes no range, which is most
    postings outside US states with pay-transparency law; `require_stated_salary` and
    `currency` therefore narrow mostly to US rows, and `min_salary` alone KEEPS unstated
    rows (it cannot rule them out). Pass currency to compare in one currency; without it,
    stated pay is compared as an annualised number in whatever currency it was stated.
    """
    _await_index()
    with session_scope() as s:
        try:
            rows = service.search_jobs(
                s, skills, remote, min_salary, limit,
                required_skills=required_skills, currency=currency,
                require_stated_salary=require_stated_salary,
                remote_scope=remote_scope, role_family=role_family, offset=offset,
                company=company, collapse_role_group=collapse_role_group,
                location=location,
            )
            if not rows and not offset:
                # A bare [] answers two different questions identically. Say which one.
                return service.diagnose_empty_search(
                    s, skills=skills, required_skills=required_skills,
                    role_family=role_family, currency=currency, company=company,
                )
            if limit > service.MAX_PAGE_SIZE:
                # You asked for more than one page holds. Returning the first page and
                # nothing else looked like the whole answer, so say it was not.
                return {
                    "results": rows,
                    "truncated": True,
                    "page_size": service.MAX_PAGE_SIZE,
                    "requested_limit": limit,
                    "hint": (
                        f"You asked for {limit} but one call returns at most "
                        f"{service.MAX_PAGE_SIZE}. This is page 1. Call again with "
                        f"offset={offset + service.MAX_PAGE_SIZE} for the next page, and "
                        "keep going until a call returns fewer rows than the page size. "
                        "get_company_info's active_jobs is the true total for one employer."
                    ),
                }
            # A half-matched search used to return rows and say nothing about the words
            # it dropped: 感知 + bev returned 20 bev rows and the reader assumed 感知 had
            # matched too. Same shape as the empty-result diagnosis, only with results.
            unknown, suggestions = service.skill_diagnostics(s, skills, required_skills)
            if unknown:
                return {
                    "results": rows,
                    "matched": len(rows),
                    "unknown_skills": unknown,
                    "suggestions": suggestions,
                    "note": (
                        f"These rows matched the OTHER tags you asked for; {unknown!r} exists "
                        "on no live posting in this index. See suggestions for the tags the "
                        "index actually uses."
                    ),
                }
            return rows
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool(
    title="Company trust signals",
    annotations=ToolAnnotations(title="Company trust signals", readOnlyHint=True,  destructiveHint=False, idempotentHint=True,  openWorldHint=False),
)
def get_company_info(company_id: str) -> dict:
    """Aggregate, anonymous trust signals for one employer.

    Returns ghost_score_avg, active_jobs, and index_built_at (when the index was last
    built). NEVER returns any individual candidate data — the server holds none.

    `claimed` is true only when the employer has claimed this tenant and we verified them by
    corporate identity — never by payment, and it never affects ranking. It is the only
    signal here that comes from the employer rather than from their public ATS data, and it
    is what makes `response_sla_days` non-null on their postings.
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.get_company_info(s, company_id)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool(
    title="Watch a job intent",
    annotations=ToolAnnotations(title="Watch a job intent", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def watch_intent(fingerprint: str, filters: dict[str, Any]) -> dict:
    """Register a standing intent so new matches can be pulled later.

    The caller supplies its OWN anonymous fingerprint (e.g. "#a3f9-k2p7-x8q1"; make it 12+
    random characters, a four-character tag collides with strangers) — the client generates
    and owns it; the server stores but can never recover it, so persist it client-side and
    pass the identical one to check_watches. Only the fingerprint and non-PII filter keys
    are stored — never a name, email, phone or résumé. Accepted filter keys mirror
    search_jobs: `skills` (ANY-overlap), `required_skills` (ALL/AND — use this to keep
    sales / solutions-architect roles out), `remote` (bool), `role_family` (e.g.
    "engineering"), `min_salary` (int), `company` (one employer, resolved at registration).
    Any other key is REFUSED (ERR_UNKNOWN_FILTER) rather than silently dropped.

    `min_salary` keeps rows with NO stated pay (they cannot be ruled out); it only drops rows
    whose stated pay is below the floor. Pay is stated mostly where law requires it (US
    postings on Greenhouse/Lever/Ashby), so a watch that needs a number will lean US.

    Returns { watch_id, status, fingerprint, existing_watches, fingerprint_notice }.
    `existing_watches` > 0 means this fingerprint was already in use; if those watches are
    not yours, pick a longer random fingerprint.
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.watch_intent(s, fingerprint, filters)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool(
    title="Refresh one employer",
    annotations=ToolAnnotations(title="Refresh one employer", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
def refresh_index(company: str) -> dict:
    """Re-crawl ONE employer's public ATS now. Takes about a minute. Throttled to 6h.

    The index is refreshed weekly, so `search_jobs` can be up to seven days behind and
    `check_watches` has nothing new to report until it moves. This is the manual nudge for
    the case that matters: the user is about to act on one employer and wants today's truth.

    Rules worth knowing before you call it:

    * ONE employer per call. A full crawl is 20+ minutes and no client will wait; a vague
      word like "robot" is refused with the list of candidates rather than fanned out into
      eleven live crawls.
    * At most one crawl per employer per 6 hours. A throttled call returns immediately with
      `refreshed: false`, `reason: "throttled"` and `last_refreshed_at` — no network request
      is made. That is not an error: it means the data you already hold is that fresh.
    * Do NOT call this speculatively or in a loop. Every call hits somebody else's public
      endpoint. Search first; refresh only when the user needs today's state of one employer.

    Args:
        company: one employer — an id ("unitree") or any part of the name in either
            language ("宇树", "XPeng"). Ambiguous input is refused, not guessed.

    Returns: `refreshed` plus `last_refreshed_at` / `next_allowed_at`; when it did run, also
    jobs_new / jobs_updated / jobs_delisted / jobs_unchanged.
    """
    _await_index()

    def _run() -> dict:
        with session_scope() as s:
            try:
                return service.refresh_company_index(s, company)
            except OpenHireError as e:
                return e.as_dict()

    # The crawler drives its own event loop with asyncio.run(). FastMCP invokes this
    # handler from inside the server's already-running loop, where that raises
    # "asyncio.run() cannot be called from a running event loop": every tester who
    # reached for "today's truth" got that traceback. A worker thread has no loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_run).result()


@mcp.tool(
    title="Check watches",
    annotations=ToolAnnotations(title="Check watches", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def check_watches(fingerprint: str) -> dict:
    """Pull matches that are new since this fingerprint's last check.

    stdio has no server push, so clients pull: call this at the start of a session.
    Returns the new matches per watch and advances each watch's last-notified marker.

    The FIRST pull on a watch returns everything matching it, not an increment: nothing
    has been reported for that watch before, so the whole standing set is new to the user.
    Each result says which it is via `is_first_pull`; do not present a first pull to the
    user as "postings that appeared since last time".

    Each result also carries `total_matching` and `truncated`: a broad watch can match
    hundreds of postings and only the 100 best-ranked are returned. Tell the user when
    `truncated` is true; the rest is not re-reported later.
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.check_watches(s, fingerprint)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool(
    title="Authorize application",
    annotations=ToolAnnotations(title="Authorize application", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def authorize_application(job_id: str, fingerprint: str, authorized: bool) -> dict:
    """Record an authorized, employer-direct application. REFUSES résumés.

    (Formerly `apply` — renamed to make explicit that this only records the user's
    authorization to apply as themselves; it never submits anything on their behalf.)

    This tool never accepts a résumé, file, cover letter, name, email or phone — a résumé
    never transits the server. It only takes a job_id, an anonymous fingerprint, and an
    explicit per-job authorization. On success it returns the apply_channel (the
    employer's own application URL) for the user to submit as themselves, plus
    resume_transmitted=false. Do NOT paste résumé content into any argument.

    Args:
        job_id: the job to apply to (from search_jobs / check_watches).
        fingerprint: the user's anonymous fingerprint.
        authorized: must be true — explicit per-job consent.
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.apply(s, job_id, fingerprint, authorized)
        except OpenHireError as e:
            return e.as_dict()


_INDEX_READY = threading.Event()
_BOOTSTRAP_STARTED = False


def _do_bootstrap() -> None:
    """Download+install the public snapshot. Runs on a worker thread; never raises."""
    from . import config
    from .db.session import dispose_engine
    from .pipeline.snapshot import install_snapshot

    db_path = config.DATABASE_URL.split(":///", 1)[-1]
    print("openhire: empty index — downloading the public snapshot (jobs/companies only)…",
          file=sys.stderr)
    try:
        dispose_engine()  # release the SQLite handle before the file is overwritten
        res = install_snapshot(config.SNAPSHOT_URL, db_path)
        print(f"openhire: snapshot ready · {res.companies} employers · {res.jobs:,} jobs · "
              f"data as of {res.data_as_of}", file=sys.stderr)
    except Exception as e:  # network / invalid snapshot: keep serving (empty) with a hint
        print(f"openhire: auto-bootstrap failed ({type(e).__name__}: {e}). "
              "Run `ohp bootstrap` manually.", file=sys.stderr)
    finally:
        _INDEX_READY.set()


def _start_bootstrap() -> None:
    """Kick off auto-bootstrap on a background thread if the index is empty.

    Startup must NOT block: `initialize` and `tools/list` need no data, and hosted
    marketplaces (ModelScope, Docker MCP Toolkit, Glama) time out a server that takes
    ~30 s to answer its first request. Tools that read data call `_await_index()`
    instead, so correctness is preserved without delaying discovery.

    Snapshot = public jobs/companies only, never user data (verified by
    install_snapshot). Skipped for Postgres and when OPENHIRE_NO_AUTO_BOOTSTRAP is set
    (tests/CI). All chatter goes to stderr — stdout belongs to the MCP protocol.
    """
    global _BOOTSTRAP_STARTED
    from sqlalchemy import func, select

    from . import config
    from .db.models import Company

    if _BOOTSTRAP_STARTED:
        return
    _BOOTSTRAP_STARTED = True
    if os.environ.get("OPENHIRE_NO_AUTO_BOOTSTRAP") or not config.DATABASE_URL.startswith("sqlite"):
        _INDEX_READY.set()
        return
    try:
        with session_scope() as s:
            n = s.execute(select(func.count()).select_from(Company)).scalar() or 0
    except Exception:
        n = 1  # can't tell: assume populated rather than clobber someone's index
    if n:
        _INDEX_READY.set()
        return

    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)  # no per-request INFO on stderr
    threading.Thread(target=_do_bootstrap, name="openhire-bootstrap", daemon=True).start()


def _await_index(timeout: float = 180.0) -> None:
    """Block until auto-bootstrap finishes.

    No-op unless `_start_bootstrap()` actually kicked one off — tools imported and called
    directly (tests, the CLI, an embedding host) must never wait on an event nobody will set.
    """
    if not _BOOTSTRAP_STARTED or _INDEX_READY.is_set():
        return
    _INDEX_READY.wait(timeout)


def serve(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the MCP server. transport: "stdio" (default) | "sse" | "streamable-http"."""
    init_db()
    _start_bootstrap()  # background: startup must stay instant for marketplace probes
    if transport != "stdio":
        mcp.settings.host = host
        mcp.settings.port = port
    mcp.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    serve()
