"""M2 acceptance — the five Claude Desktop scripts, driven through the real MCP protocol.

Uses the in-memory client↔server session so tools are exercised exactly as a Claude
Desktop client would: initialize handshake, list_tools, call_tool. The global test DB is
the throwaway SQLite from conftest.py.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect
from sqlalchemy import select

from openhire.db import Watch, init_db, session_scope
from openhire.db.models import Company, Job
from openhire.mcp_server import mcp

UTC = dt.timezone.utc


def _payload(res):
    """Unwrap a CallToolResult into the tool's return value.

    FastMCP wraps list returns as structuredContent={"result": [...]} but leaves
    structuredContent=None for dict returns (JSON lives in the text block).
    """
    sc = res.structuredContent
    if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
        return sc["result"]
    if sc is not None:
        return sc
    return json.loads(res.content[0].text) if res.content else None


def _mkjob(jid, cid, title, skills, remote, salary=None, when=None):
    when = when or dt.datetime.now(UTC)
    smin, smax, cur = salary if salary else (None, None, None)
    return Job(
        id=f"{cid}:{jid}", company_id=cid, title=title, description_raw=title,
        skills=skills, remote_policy=remote, salary_min=smin, salary_max=smax,
        salary_currency=cur, salary_inferred=False,
        location="Remote" if remote == "remote" else "NYC",
        first_seen_at=when, verified_at=when, source="ats_public_api",
        apply_channel=f"https://boards.greenhouse.io/embed/job_app?for={cid}&token={jid}",
        content_hash=f"h{jid}", ghost_score=0.0,
    )


@pytest.fixture()
def seeded():
    init_db()
    now = dt.datetime.now(UTC)
    with session_scope() as s:
        # Clean slate for a deterministic run.
        for t in (Job, Company, Watch):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", verified=False, last_crawled_at=now))
        s.add(Company(id="beta", name="Beta Labs", ats_vendor="lever", ats_tenant="beta",
                      careers_url="y", verified=True, last_crawled_at=now))
        s.add(_mkjob("1", "acme", "LLM Platform Engineer", ["rust", "k8s", "rag"], "remote"))
        s.add(_mkjob("2", "acme", "Java Backend", ["java"], "onsite"))
        s.add(_mkjob("4", "beta", "Senior Rust Engineer", ["rust"], "remote",
                     salary=(650000, 800000, "USD")))
    return now


async def test_all_five_acceptance_scripts(seeded):
    async with connect(mcp) as client:
        # The client can discover exactly the four protocol tools + apply.
        tools = {t.name for t in (await client.list_tools()).tools}
        assert tools == {
            "search_jobs", "get_company_info", "watch_intent", "check_watches",
            "authorize_application",
        }

        # --- Script 1: search remote Rust/K8s infra jobs ----------------------
        r = _payload(await client.call_tool(
            "search_jobs", {"skills": ["rust", "k8s"], "remote": True}
        ))
        assert isinstance(r, list) and len(r) >= 1
        for job in r:
            assert job["verified_at"] and job["ghost_score"] is not None
            assert job["apply_channel"].startswith("https://")
            assert job["remote_policy"] == "remote"  # genuinely remote
        first_company = r[0]["company_id"]

        # --- Script 2: is the first company legit / a ghost job? --------------
        info = _payload(await client.call_tool(
            "get_company_info", {"company_id": first_company}
        ))
        assert set(info) == {
            "company_id", "company", "ghost_score_avg", "active_jobs", "index_built_at",
        }
        blob = str(info).lower()
        for pii in ("fingerprint", "email", "resume", "candidate", "applicant"):
            assert pii not in blob  # aggregate signals only

        # --- Script 3: watch these for me ------------------------------------
        w = _payload(await client.call_tool(
            "watch_intent",
            {"fingerprint": "#a3f9", "filters": {"skills": ["rust", "k8s"], "remote": True}},
        ))
        assert w["watch_id"].startswith("w_") and w["status"] == "active"
        # The stored watch carries ONLY an anonymous fingerprint + filters.
        with session_scope() as s:
            row = s.execute(select(Watch).where(Watch.watch_id == w["watch_id"])).scalars().one()
            assert row.fingerprint == "#a3f9"
            assert set(row.filters) <= {"skills", "remote", "min_salary"}

        # --- Script 4: cross-session pull ------------------------------------
        # First pull advances the notification marker.
        _payload(await client.call_tool("check_watches", {"fingerprint": "#a3f9"}))
        # A new matching job lands later (simulating a fresh crawl in another session).
        with session_scope() as s:
            s.add(_mkjob("77", "beta", "Staff Rust/K8s Engineer", ["rust", "k8s"], "remote",
                         when=dt.datetime.now(UTC) + dt.timedelta(seconds=1)))
        second = _payload(await client.call_tool("check_watches", {"fingerprint": "#a3f9"}))
        new_ids = {m["job_id"] for res in second["results"] for m in res["new_matches"]}
        assert "beta:77" in new_ids  # the increment is returned

        # --- Script 5: adversarial résumé (red line #1) ----------------------
        # Résumé content crammed into the fingerprint must be refused, with a reason.
        resume = "Name: Jane Doe\nEmail: jane@x.com\n" + "experience " * 40
        refused = _payload(await client.call_tool(
            "authorize_application",
            {"job_id": r[0]["job_id"], "fingerprint": resume, "authorized": True}
        ))
        assert refused["error"] == "ERR_RESUME_NEVER_TRANSMITTED"
        assert "never transits" in refused["message"].lower() or \
               "never transit" in refused["message"].lower()

        # A proper authorized application returns only a receipt + apply_channel; no résumé.
        ok = _payload(await client.call_tool(
            "authorize_application",
            {"job_id": r[0]["job_id"], "fingerprint": "#a3f9", "authorized": True}
        ))
        assert ok["resume_transmitted"] is False
        assert ok["apply_channel"].startswith("https://")
        assert ok["receipt_id"].startswith("r_")


async def test_apply_tool_has_no_resume_parameter(seeded):
    """Structural guarantee: authorize_application exposes no résumé/file parameter."""
    async with connect(mcp) as client:
        apply_tool = next(
            t for t in (await client.list_tools()).tools if t.name == "authorize_application"
        )
        props = set(apply_tool.inputSchema.get("properties", {}))
        assert props == {"job_id", "fingerprint", "authorized"}
        for pii in ("resume", "cv", "file", "attachment", "email", "name"):
            assert pii not in props
