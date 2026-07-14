"""Index snapshot: build (maintainer) + install (bootstrap).

The snapshot is a PUBLIC-DATA-ONLY SQLite image of the index — it contains ONLY the
`companies` and `jobs` tables. Any user-state table (`watches`, `applications`) and any
fingerprint MUST be zero rows. This is a privacy red line: the snapshot is published as a
GitHub Release asset, so it can never carry a single row of user state. `build_snapshot`
enforces this at build time and RAISES (fails the build) on any violation.

The snapshot is intentionally NOT shipped inside the wheel (keeps the package tiny and the
data fresh) — `ohp bootstrap` downloads it, then an incremental ingest refreshes it live.
"""

from __future__ import annotations

import datetime as dt
import gzip
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _tempfile(suffix: str) -> Path:
    """A temp path whose fd is closed immediately (Windows can't unlink an open fd)."""
    fd, p = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(p)

# Only these tables are copied into a snapshot. Everything else stays empty.
_PUBLIC_TABLES = ("companies", "jobs")
# These must be zero rows in any published snapshot (privacy red line).
_USER_STATE_TABLES = ("watches", "applications")


class SnapshotError(RuntimeError):
    pass


@dataclass
class SnapshotBuildResult:
    path: Path
    companies: int
    jobs: int
    gz_bytes: int
    data_as_of: str | None  # max(verified_at) ISO — the snapshot's freshness anchor


@dataclass
class SnapshotInstallResult:
    companies: int
    jobs: int
    data_as_of: str | None
    age_days: int | None


def _shared_columns(dest: sqlite3.Connection, src: sqlite3.Connection, table: str) -> list[str]:
    d = [r[1] for r in dest.execute(f"PRAGMA table_info({table})").fetchall()]
    s = {r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()}
    # Preserve dest column order; only copy columns present in BOTH (schema-drift safe).
    return [c for c in d if c in s]


def _max_verified_at(conn: sqlite3.Connection) -> str | None:
    try:
        return conn.execute("SELECT max(verified_at) FROM jobs").fetchone()[0]
    except sqlite3.Error:
        return None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def build_snapshot(source_db_path: str, dest_gz_path: str) -> SnapshotBuildResult:
    """Build a companies+jobs-only gzipped snapshot from a source DB. Raises on any
    user-state leak. `source_db_path` is a plain filesystem path to the SQLite file."""
    src_path = Path(source_db_path)
    if not src_path.exists():
        raise SnapshotError(f"source DB not found: {src_path}")

    tmp_db = _tempfile(".db")
    try:
        dest = sqlite3.connect(tmp_db)
        try:
            dest.execute("ATTACH DATABASE ? AS src", (str(src_path),))
            copied = {}
            # Recreate ONLY the public tables, using the SOURCE's exact DDL (so nullability
            # / migrated columns match and no user-state table is ever even created here).
            for table in _PUBLIC_TABLES:
                ddl = dest.execute(
                    "SELECT sql FROM src.sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                if not ddl or not ddl[0]:
                    raise SnapshotError(f"source is missing table {table!r}")
                dest.execute(ddl[0])
                cols = [r[1] for r in dest.execute(f"PRAGMA table_info({table})").fetchall()]
                collist = ", ".join(cols)
                dest.execute(
                    f"INSERT INTO {table} ({collist}) SELECT {collist} FROM src.{table}"
                )
                copied[table] = dest.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            dest.commit()

            # RED LINE: user-state tables must not even exist in the snapshot (and if a
            # future change creates them, they must be empty).
            for t in _USER_STATE_TABLES:
                if _table_exists(dest, t):
                    n = dest.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                    if n != 0:
                        raise SnapshotError(
                            f"snapshot build REFUSED: {t} has {n} rows — a snapshot must "
                            "contain ZERO user-state rows (privacy red line)."
                        )
            if copied.get("jobs", 0) == 0:
                raise SnapshotError("snapshot build REFUSED: 0 jobs (empty index).")
            data_as_of = _max_verified_at(dest)
        finally:
            dest.close()

        dest_gz = Path(dest_gz_path)
        dest_gz.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_db, "rb") as f_in, gzip.open(dest_gz, "wb", compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)

        return SnapshotBuildResult(
            path=dest_gz,
            companies=copied.get("companies", 0),
            jobs=copied.get("jobs", 0),
            gz_bytes=dest_gz.stat().st_size,
            data_as_of=data_as_of,
        )
    finally:
        tmp_db.unlink(missing_ok=True)


def _fetch_to(url: str, dest: Path) -> None:
    """Download a URL (http/https) or copy a local path / file:// to dest."""
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        import httpx

        with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    else:
        src = Path(parsed.path if parsed.scheme == "file" else url)
        if not src.exists():
            raise SnapshotError(f"snapshot not found at {src}")
        shutil.copyfile(src, dest)


def install_snapshot(url: str, db_path: str) -> SnapshotInstallResult:
    """Download+decompress a snapshot into db_path. Verifies public-only content before
    installing (never write user-state). Overwrites db_path."""
    tmp_gz = _tempfile(".db.gz")
    tmp_db = _tempfile(".db")
    try:
        _fetch_to(url, tmp_gz)
        with gzip.open(tmp_gz, "rb") as f_in, open(tmp_db, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

        conn = sqlite3.connect(tmp_db)
        try:
            jobs = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
            companies = conn.execute("SELECT count(*) FROM companies").fetchone()[0]
            for t in _USER_STATE_TABLES:
                try:
                    n = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                except sqlite3.Error:
                    n = 0
                if n != 0:
                    raise SnapshotError(
                        f"downloaded snapshot is invalid: {t} has {n} rows (must be 0)."
                    )
            if jobs == 0:
                raise SnapshotError("downloaded snapshot has 0 jobs.")
            data_as_of = _max_verified_at(conn)
        finally:
            conn.close()

        target = Path(db_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp_db, target)
        # Clear any stale WAL sidecars from a previous DB at this path.
        for side in (target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")):
            side.unlink(missing_ok=True)

        return SnapshotInstallResult(
            companies=companies, jobs=jobs, data_as_of=data_as_of,
            age_days=_age_days(data_as_of),
        )
    finally:
        tmp_gz.unlink(missing_ok=True)
        tmp_db.unlink(missing_ok=True)


def _age_days(data_as_of: str | None) -> int | None:
    if not data_as_of:
        return None
    try:
        d = dt.datetime.fromisoformat(str(data_as_of))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - d).days
    except ValueError:
        return None
