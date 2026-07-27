"""Tiny forward-only migrations (add-column-if-missing).

SQLAlchemy's create_all never ALTERs existing tables, so when we add columns to a model
we add them to a live DB here. Idempotent and dialect-aware (SQLite / Postgres).
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from .session import get_engine, init_db

# name -> (sqlite_type, postgres_type)
_EXTRACTION_COLUMNS = {
    "extraction_source": ("TEXT", "TEXT"),
    "skills_fallback": ("TEXT", "TEXT[]"),
    "remote_policy_fallback": ("TEXT", "TEXT"),
    "salary_min_fallback": ("INTEGER", "INT"),
    "salary_max_fallback": ("INTEGER", "INT"),
    "salary_currency_fallback": ("TEXT", "TEXT"),
    # Real ATS posting dates (P0-2): datePosted / ghost_score age anchor on these.
    "posted_at": ("TIMESTAMP", "TIMESTAMPTZ"),
    "updated_at": ("TIMESTAMP", "TIMESTAMPTZ"),
    # Coarse job family — column frozen now; population pending a DeepSeek pass.
    "role_family": ("TEXT", "TEXT"),
    # annual | monthly — the period the employer published the pay in (v0.2).
    "salary_period": ("TEXT", "TEXT"),
}


def ensure_schema() -> list[str]:
    """Create tables if absent, then add any missing columns. Returns columns added."""
    init_db()
    engine = get_engine()
    dialect = engine.dialect.name
    added: list[str] = []

    existing = {c["name"] for c in inspect(engine).get_columns("jobs")}
    with engine.begin() as conn:
        for name, (sqlite_t, pg_t) in _EXTRACTION_COLUMNS.items():
            if name in existing:
                continue
            col_type = pg_t if dialect == "postgresql" else sqlite_t
            conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {col_type}"))
            added.append(name)
        if "extraction_source" in added:
            conn.execute(
                text("UPDATE jobs SET extraction_source = 'heuristic' "
                     "WHERE extraction_source IS NULL")
            )
        if "salary_period" in added:
            # Every pre-v0.2 row came from a Western ATS quoting annual pay; the Chinese
            # portals (Beisen) quote 月薪, so those are corrected to monthly.
            conn.execute(
                text("UPDATE jobs SET salary_period = 'annual' WHERE salary_period IS NULL")
            )
            conn.execute(
                text(
                    "UPDATE jobs SET salary_period = 'monthly' WHERE company_id IN "
                    "(SELECT id FROM companies WHERE ats_vendor = 'beisen')"
                )
            )
    return added
