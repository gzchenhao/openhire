"""OpenHire MCP server (FastMCP, stdio transport).

Exposes the four protocol tools + apply. Tool docstrings are the descriptions the agent
reads, so they carry the privacy contract verbatim. Each tool is a thin wrapper over the
transport-agnostic `service` layer; OpenHireError is surfaced as a structured
`{error, message}` result so the agent gets a clear reason instead of a transport crash.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import service
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


@mcp.tool()
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


@mcp.tool()
def get_company_info(company_id: str) -> dict:
    """Aggregate, anonymous trust signals for one employer.

    Returns ghost_score_avg, active_jobs, and index_built_at (when the index was last
    built). NEVER returns any individual candidate data — the server holds none.
    """
    with session_scope() as s:
        try:
            return service.get_company_info(s, company_id)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool()
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
    with session_scope() as s:
        try:
            return service.watch_intent(s, fingerprint, filters)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool()
def check_watches(fingerprint: str) -> dict:
    """Pull matches that are new since this fingerprint's last check.

    stdio has no server push, so clients pull: call this at the start of a session.
    Returns the new matches per watch and advances each watch's last-notified marker.
    """
    with session_scope() as s:
        try:
            return service.check_watches(s, fingerprint)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool()
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
    with session_scope() as s:
        try:
            return service.apply(s, job_id, fingerprint, authorized)
        except OpenHireError as e:
            return e.as_dict()


def serve() -> None:
    """Start the stdio MCP server."""
    init_db()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    serve()
