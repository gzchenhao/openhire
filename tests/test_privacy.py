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


def test_apply_tool_refuses_an_undeclared_resume_argument_over_the_wire():
    """Round 8: the docstring said REFUSES, but FastMCP's argument model ignores extra
    keys and its handler skips input validation, so {"resume": "..."} reached the tool
    with the résumé silently dropped and a receipt recorded as if nothing had happened.
    The refusal now happens where the raw arguments still exist, with our own code."""
    import asyncio
    import json

    from mcp.shared.memory import create_connected_server_and_client_session as connect
    from sqlalchemy import select

    from openhire.db import Application, init_db, session_scope
    from openhire.mcp_server import mcp

    def _payload(res):
        sc = res.structuredContent
        if isinstance(sc, dict) and set(sc) == {"result"}:
            return sc["result"]
        return sc if sc is not None else json.loads(res.content[0].text)

    async def _call(args):
        async with connect(mcp) as client:
            return _payload(await client.call_tool("authorize_application", args))

    init_db()
    with session_scope() as s:
        before = s.scalar(select(__import__("sqlalchemy").func.count()).select_from(Application)) or 0

    for smuggled in ({"resume": "Jane Doe, 10 years of perception"}, {"cv": "..."},
                     {"file": "cv.pdf"}, {"email": "jane@example.com"}, {"notes": "see attached"}):
        out = asyncio.run(_call({"job_id": "acme:1", "fingerprint": "#a3f9-k2p7-x8q1",
                                 "authorized": True, **smuggled}))
        assert out["error"] == "ERR_PII_NOT_ACCEPTED", smuggled
        assert "Nothing was recorded" in out["message"]
        assert next(iter(smuggled)) in out["message"]

    with session_scope() as s:
        after = s.scalar(select(__import__("sqlalchemy").func.count()).select_from(Application)) or 0
    assert after == before, "a refused call must not leave a receipt"

    # The declared arguments alone still reach the service (which answers for the job).
    out = asyncio.run(_call({"job_id": "no-such:1", "fingerprint": "#a3f9-k2p7-x8q1",
                             "authorized": True}))
    assert out["error"] == "ERR_JOB_NOT_FOUND"

    # watch_intent has the same exposure and the same answer.
    async def _watch(args):
        async with connect(mcp) as client:
            return _payload(await client.call_tool("watch_intent", args))

    out = asyncio.run(_watch({"fingerprint": "#a3f9-k2p7-x8q1", "filters": {"skills": ["rust"]},
                              "resume": "..."}))
    assert out["error"] == "ERR_PII_NOT_ACCEPTED"


# --- version must never drift (a tester found the banner reporting 0.3.2 on 0.4.1) ---
def test_version_matches_pyproject():
    """`openhire.__version__` comes from installed metadata, so it can only drift if the
    editable install is stale or a release shipped mismatched metadata. Either way the
    user-visible `ohp version` banner would lie, which is how 0.4.0/0.4.1 both shipped
    reporting "0.3.2"."""
    import tomllib
    from pathlib import Path

    import openhire

    if openhire.__version__.endswith("+dev"):
        return  # source tree with no install (PYTHONPATH=src) — nothing to compare against
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject.exists():  # running against an installed wheel, nothing to compare
        return
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert openhire.__version__ == declared, (
        f"openhire.__version__={openhire.__version__} but pyproject says {declared}. "
        "Run `pip install -e .` after a version bump."
    )


def test_version_flag_exists_alongside_the_subcommand():
    """`--version` is the convention every CLI user reaches for first. The subcommand
    existed; the flag did not, and `ohp --version` answered "No such option"."""
    from typer.testing import CliRunner

    import openhire
    from openhire.cli import app

    runner = CliRunner()
    for argv in (["--version"], ["-V"]):
        res = runner.invoke(app, argv)
        assert res.exit_code == 0, argv
        assert openhire.__version__ in res.stdout, argv


def test_numbers_export_names_what_each_figure_counts():
    """Round 3 caught "139 employers" in every article against 140 rows in the table. It was
    never a wrong number — it was two different questions wearing one label. This file is
    the single source for public claims, so each key has to say what it counts."""
    import json

    from typer.testing import CliRunner

    from openhire.cli import app

    import tempfile
    from pathlib import Path

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "n.json"
        res = runner.invoke(app, ["numbers", "--out", str(out)])
        assert res.exit_code == 0, res.output
        data = json.loads(out.read_text(encoding="utf-8"))

    # The two counts that were conflated must both exist, separately named.
    assert "companies_in_index" in data
    assert "employers_with_live_postings" in data
    assert data["employers_with_live_postings"] <= data["companies_in_index"]
    for key in ("live_postings", "median_days_open", "pct_open_over_180d", "generated_at"):
        assert key in data


def test_shipped_cli_copy_does_not_carry_the_retired_persona():
    """Outward-copy rule 2 (CLAUDE.md): the narrative is "deep-tech recruiter". "一个不写
    代码的 PM" was the identity we retired, and it was still in the one-time star hint —
    the single most-read piece of outward copy we ship, since every CLI user sees it once.
    A rule we break in the product is not a rule."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "openhire"
    offenders = [
        p.name for p in src.rglob("*.py")
        if "不写代码" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"retired persona still shipped in: {offenders}"
