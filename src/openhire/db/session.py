"""Engine + session factory. Creates the schema on first use for SQLite dev."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .. import config
from .models import Base

_engine = None
_Session: sessionmaker | None = None


def _make_engine():
    url = config.DATABASE_URL
    if url.startswith("sqlite"):
        # Ensure the parent directory for the SQLite file exists.
        db_path = url.split(":///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # A long-running stdio MCP server interleaves streaming reads (search/check over
        # ~12k rows) with writes (watch_intent/apply). Under the default rollback journal,
        # an open reader blocks the writer → the writer stalls on the busy timeout and, in
        # the async event loop, surfaces as a multi-minute hang (P0-1). WAL lets one writer
        # run concurrently with readers; busy_timeout bounds any genuine contention; and
        # check_same_thread=False lets pooled connections cross the FastMCP worker threads.
        engine = create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _rec):  # pragma: no cover - trivial DDL
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        return engine
    return create_engine(url, future=True, pool_pre_ping=True)


def get_engine():
    global _engine, _Session
    if _engine is None:
        _engine = _make_engine()
        _Session = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _engine


def init_db() -> None:
    """Create all tables if they do not exist, then add any columns this build expects.

    The migration is here and not at each call site because the database we open is very
    often NOT one we created: a new user bootstraps from the published snapshot, which was
    built by whatever version was current when it was last refreshed. Creating the tables
    but not migrating them is what let v0.6.0 crash on first search against the 09-07
    snapshot. Both halves are idempotent and cost two PRAGMA reads on an up-to-date file.
    """
    Base.metadata.create_all(get_engine())
    from .migrate import add_missing_columns  # local: migrate imports this module

    add_missing_columns()


def dispose_engine() -> None:
    """Close the engine and drop the cached factory so the next call rebuilds it.

    Needed before overwriting the SQLite file (e.g. installing a snapshot): on Windows an
    open pooled connection holds a lock that blocks the file replacement."""
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None


@contextmanager
def session_scope() -> Session:
    """Transactional session context manager."""
    get_engine()
    assert _Session is not None
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dialect_name() -> str:
    return urlparse(config.DATABASE_URL).scheme.split("+")[0]
