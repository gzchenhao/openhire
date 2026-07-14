"""Privacy red-line tests (README §三条隐私红线).

CI MUST stay green on these. This file covers the red lines that apply to M1's code:

  Red line #1 — PII never transits/persists on the server.
      * `watches` and `applications` carry NO PII column (ORM + schema.sql).
      * identity is only an anonymous fingerprint.
  Red line #3 — pay only for outcomes; v0.1 has NO billing code at all.
      * source tree contains no billing / paid-exposure / sponsored-ranking machinery.

Red line #2 (ranking is never a paid parameter) is enforced by tests that ship with the
ranking function in M2 (search_jobs); see test_ranking.py once that lands.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from openhire.db.models import Application, Watch

SRC = Path(__file__).resolve().parent.parent / "src" / "openhire"

# Substrings that would indicate a personal-data column snuck in.
PII_TOKENS = [
    "name",  # note: allowed as part of other words is handled below
    "email",
    "phone",
    "resume",
    "cv",
    "ssn",
    "address",
    "dob",
    "birth",
    "gender",
    "photo",
    "avatar",
    "linkedin",
    "github_url",
    "first_name",
    "last_name",
    "full_name",
]

# Columns legitimately present that must not be misread as PII.
ALLOWED_COLUMNS = {
    "watches": {
        "watch_id",
        "fingerprint",
        "filters",
        "created_at",
        "last_notified_at",
        "active",
    },
    "applications": {
        "receipt_id",
        "job_id",
        "fingerprint",
        "authorized",
        "delivered_via",
        "created_at",
    },
}


def _column_names(model) -> set[str]:
    return {col.name for col in model.__table__.columns}


@pytest.mark.parametrize("model", [Watch, Application])
def test_no_unexpected_columns(model):
    """Only the whitelisted columns may exist on identity-bearing tables."""
    table = model.__tablename__
    cols = _column_names(model)
    assert cols == ALLOWED_COLUMNS[table], (
        f"{table} columns changed: {cols ^ ALLOWED_COLUMNS[table]} — "
        "any new column on this table risks the no-PII red line."
    )


@pytest.mark.parametrize("model", [Watch, Application])
def test_no_pii_token_in_columns(model):
    cols = _column_names(model)
    for col in cols:
        low = col.lower()
        for tok in PII_TOKENS:
            # 'name'/'cv' only flag as whole-word-ish matches, not substrings like
            # 'company_name' would — but we don't allow those columns anyway.
            if re.search(rf"(^|_){re.escape(tok)}($|_)", low):
                pytest.fail(f"{model.__tablename__}.{col} looks like PII (token '{tok}')")


def test_identity_is_only_fingerprint():
    assert "fingerprint" in _column_names(Watch)
    assert "fingerprint" in _column_names(Application)


def test_schema_sql_matches_no_pii():
    """The canonical Postgres DDL must agree with the ORM (no PII columns)."""
    ddl = (SRC / "db" / "schema.sql").read_text(encoding="utf-8")
    for table, allowed in ALLOWED_COLUMNS.items():
        block = _extract_create_table(ddl, table)
        cols = _columns_from_ddl(block)
        assert cols == allowed, f"schema.sql {table} columns {cols} != {allowed}"


def _extract_create_table(ddl: str, table: str) -> str:
    m = re.search(rf"CREATE TABLE {table} \((.*?)\n\);", ddl, re.S)
    assert m, f"CREATE TABLE {table} not found in schema.sql"
    return m.group(1)


def _columns_from_ddl(block: str) -> set[str]:
    cols = set()
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        if line.upper().startswith(("REFERENCES", "PRIMARY KEY", "FOREIGN KEY", "CHECK")):
            continue
        token = line.split()[0]
        if token.isidentifier():
            cols.add(token)
    return cols


# --- Red line #3: no billing code in v0.1 ------------------------------------
FORBIDDEN_BILLING = [
    "stripe",
    "invoice",
    "billing",
    "charge_card",
    "sponsored",
    "promoted_rank",
    "boost_rank",
    "paid_placement",
    "cpc",
    "cpm",
    "price_per_click",
]


def test_no_billing_code_in_v01():
    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for tok in FORBIDDEN_BILLING:
            if tok in text:
                offenders.append(f"{path.name}: {tok}")
    assert not offenders, (
        "v0.1 must contain no billing / paid-exposure code (red line #3): "
        + ", ".join(offenders)
    )


def test_source_is_first_party_only():
    """`source` (protocol field ②) must never be a job board — only first-party."""
    from openhire.pipeline.ingest import SOURCE_ATS

    assert SOURCE_ATS in ("employer_site", "ats_public_api")


# --- Red line #1 (API): apply refuses résumés/files --------------------------
def test_apply_guard_rejects_resume_payload():
    import pytest

    from openhire.errors import OpenHireError
    from openhire.service import assert_no_resume

    for bad in ({"resume": "..."}, {"cv": "..."}, {"file": "..."},
                {"attachment": "..."}, {"email": "a@b.c"}, {"cover_letter": "..."}):
        with pytest.raises(OpenHireError) as e:
            assert_no_resume(bad)
        assert e.value.code == "ERR_RESUME_NEVER_TRANSMITTED"

    # A clean call (no résumé keys) must pass.
    assert_no_resume({"job_id": "x:1", "fingerprint": "#a3f9", "authorized": True}) is None


def test_apply_tool_exposes_no_resume_parameter():
    """The MCP authorize_application tool has no résumé/file parameter — can't be sent."""
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session as connect

    from openhire.db import init_db
    from openhire.mcp_server import mcp

    async def _props():
        init_db()
        async with connect(mcp) as client:
            tool = next(
                t for t in (await client.list_tools()).tools
                if t.name == "authorize_application"
            )
            return set(tool.inputSchema.get("properties", {}))

    props = asyncio.run(_props())
    assert props == {"job_id", "fingerprint", "authorized"}
    assert not (props & {"resume", "cv", "file", "attachment", "email", "name", "phone"})
