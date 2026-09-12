"""OpenHire MCP server (FastMCP; stdio by default, sse / streamable-http optional).

Exposes the four protocol tools + apply. Tool docstrings are the descriptions the agent
reads, so they carry the privacy contract verbatim. Each tool is a thin wrapper over the
transport-agnostic `service` layer; OpenHireError is surfaced as a structured
`{error, message}` result so the agent gets a clear reason instead of a transport crash.
"""

from __future__ import annotations

import os
import sys
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
        "OpenHire is an agent-native job protocol over public ATS data. A résumé or any "
        "PII NEVER transits this server — only an anonymous, client-generated fingerprint "
        "(e.g. '#a3f9'). Matching happens on the client. Use search_jobs to hard-filter "
        "the live index (results carry verified_at, ghost_score and apply_channel); "
        "get_company_info for aggregate trust signals; watch_intent to register a standing "
        "intent; check_watches to pull new hits; authorize_application to record an "
        "authorized, employer-direct application. Never pass a résumé, file, name, email or "
        "phone to any tool."
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
) -> list[dict] | dict:
    """Search the live job index by hard filters; returns ranked JobPosting[].

    The server does ONLY a hard filter plus a fixed ranking of match-quality × freshness —
    precise re-ranking is left to you, the client, which holds the user's context. Every
    result includes the five protocol fields (verified_at, source, ghost_score,
    response_sla_days, apply_channel) plus datePosted, days_open, remote_scope and
    eligible_regions.

    Args:
        skills: skill tags, ANY-overlap match (union), e.g. ["rust", "k8s"].
        required_skills: skills that must ALL be present (AND), e.g. ["rust"].
        remote: if true, only fully-remote roles.
        remote_scope: filter remote roles by reach: "worldwide" | "region_locked" |
            "country_locked".
        min_salary: salary floor. By default roles with NO stated pay are KEPT (they can't
            be ruled out); set require_stated_salary=true to drop them.
        currency: restrict to a stated-pay currency, e.g. "USD" (implies stated pay).
        require_stated_salary: if true, drop roles that publish no salary.
        role_family: coarse family filter, e.g. "engineering" (v0.1: unpopulated → no-op).
        limit: max results (default 20).
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.search_jobs(
                s, skills, remote, min_salary, limit,
                required_skills=required_skills, currency=currency,
                require_stated_salary=require_stated_salary,
                remote_scope=remote_scope, role_family=role_family,
            )
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

    The caller supplies its OWN anonymous fingerprint (e.g. "#a3f9") — the client generates
    and owns it; the server stores but can never recover it, so persist it client-side and
    pass the identical one to check_watches. Only the fingerprint and non-PII filter keys
    are stored — never a name, email, phone or résumé. Accepted filter keys mirror
    search_jobs: `skills` (ANY-overlap), `required_skills` (ALL/AND — use this to keep
    sales / solutions-architect roles out), `remote` (bool), `role_family` (e.g.
    "engineering"), `min_salary` (int). Returns { watch_id, status, fingerprint,
    fingerprint_notice }.
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.watch_intent(s, fingerprint, filters)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool(
    title="Check watches",
    annotations=ToolAnnotations(title="Check watches", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def check_watches(fingerprint: str) -> dict:
    """Pull matches that are new since this fingerprint's last check.

    stdio has no server push, so clients pull: call this at the start of a session.
    Returns the new matches per watch and advances each watch's last-notified marker.
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
