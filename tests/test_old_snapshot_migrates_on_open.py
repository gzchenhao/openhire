"""Opening a database built by an OLDER version must migrate it, not crash.

2026-09-14/15: v0.6.0 went to PyPI carrying two new `companies` columns
(response_sla_days, claimed_at) while the published snapshot still predated them.
A new user bootstraps FROM that snapshot, so `uvx openhire@latest serve` crashed on
the first search with `no such column: companies.response_sla_days`, and the weekly
refresh workflow died the same way at `ohp seed`.

The release rule we already had — publish to PyPI before refreshing the snapshot —
only guards OLD client + NEW data. This was NEW client + OLD data: the same fault
through the other door. So the fix is not another rule, it is migrating on open.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import inspect

from openhire.db import session as session_mod

# Exactly the companies table as the 2026-09-07 published snapshot had it.
_PRE_MIGRATION_COMPANIES = """
CREATE TABLE companies (
    id VARCHAR NOT NULL PRIMARY KEY,
    name VARCHAR NOT NULL,
    ats_vendor VARCHAR,
    ats_tenant VARCHAR,
    careers_url VARCHAR,
    verified BOOLEAN,
    last_crawled_at TIMESTAMP
)
"""


@pytest.fixture()
def old_db(tmp_path, monkeypatch):
    path = tmp_path / "published.db"
    con = sqlite3.connect(path)
    con.execute(_PRE_MIGRATION_COMPANIES)
    con.execute("INSERT INTO companies (id, name, ats_vendor, ats_tenant) "
                "VALUES ('mongodb', 'MongoDB', 'greenhouse', 'mongodb')")
    con.commit()
    con.close()

    # config.DATABASE_URL is read at import, so the env var alone would do nothing.
    from openhire import config

    monkeypatch.setattr(
        config, "DATABASE_URL", f"sqlite+pysqlite:///{path.as_posix()}"
    )
    session_mod.dispose_engine()
    yield path
    session_mod.dispose_engine()


def test_a_snapshot_from_an_older_version_is_migrated_not_rejected(old_db):
    before = {c["name"] for c in inspect(session_mod.get_engine()).get_columns("companies")}
    assert "response_sla_days" not in before, "fixture must start pre-migration"

    session_mod.init_db()

    after = {c["name"] for c in inspect(session_mod.get_engine()).get_columns("companies")}
    assert {"response_sla_days", "claimed_at"} <= after
    # And the row that was already there survives the ALTER.
    with session_mod.session_scope() as s:
        from openhire.db import Company

        assert s.get(Company, "mongodb").name == "MongoDB"


def test_a_real_query_against_the_migrated_snapshot_does_not_raise(old_db):
    """The actual failure mode: not the ALTER, but the first SELECT that names the
    new columns. Reproduced end to end rather than asserting on schema alone."""
    from sqlalchemy import select

    from openhire.db import Company

    session_mod.init_db()
    with session_mod.session_scope() as s:
        rows = list(s.execute(select(Company).where(Company.id.in_(["mongodb"]))).scalars())
    assert [c.id for c in rows] == ["mongodb"]
    assert rows[0].response_sla_days is None
