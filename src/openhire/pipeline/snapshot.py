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
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname


def _local_path(url: str) -> Path:
    """A local source given as a path or a file:// URL, as a filesystem path.

    `urlparse("file:///C:/x/y.gz").path` is "/C:/x/y.gz", which Windows reads as a path
    with an extra leading backslash and cannot find (3 tests failed there on 0.8.12);
    `url2pathname` turns the URL path into the platform's own spelling on every OS."""
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(url2pathname(parsed.path))
    return Path(url)


def _tempfile(suffix: str) -> Path:
    """A temp path whose fd is closed immediately (Windows can't unlink an open fd)."""
    fd, p = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(p)

# Only these tables are copied into a snapshot. Everything else stays empty.
_PUBLIC_TABLES = ("companies", "jobs")
# These must be zero rows in any published snapshot (privacy red line).
_USER_STATE_TABLES = ("watches", "applications")
# Employers a user added to their own index (companies.user_added = 1, 0.8.13) and their
# postings are the user's too: never published in a snapshot, carried over on every refresh.
_USER_ADDED_COLUMN = "user_added"


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


def _has_column(conn: sqlite3.Connection, table: str, column: str, schema: str = "main") -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall())


def _user_added_rows(conn: sqlite3.Connection, schema: str = "main") -> int:
    """How many employers in this database are a user's own additions (0 when the column
    predates this version)."""
    if schema == "main" and not _table_exists(conn, "companies"):
        return 0
    if not _has_column(conn, "companies", _USER_ADDED_COLUMN, schema):
        return 0
    return conn.execute(f"SELECT count(*) FROM {schema}.companies WHERE {_USER_ADDED_COLUMN} = 1").fetchone()[0]


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
                # A user's own employers (and their postings) are user state in all but
                # name: they say where that person is looking. They never leave the machine.
                where = ""
                if _USER_ADDED_COLUMN in cols:
                    if table == "companies":
                        where = f" WHERE {_USER_ADDED_COLUMN} IS NOT 1"
                elif table == "jobs" and _has_column(dest, "companies", _USER_ADDED_COLUMN, "src"):
                    where = f" WHERE company_id NOT IN (SELECT id FROM src.companies WHERE {_USER_ADDED_COLUMN} = 1)"
                dest.execute(
                    f"INSERT INTO {table} ({collist}) SELECT {collist} FROM src.{table}{where}"
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


FETCH_ATTEMPTS = 4


def _fetch_to(url: str, dest: Path, attempts: int = FETCH_ATTEMPTS) -> None:
    """Download a URL (http/https) or copy a local path / file:// to dest.

    Resumable. The asset is ~30 MB on GitHub's CDN, and from a slow or lossy route (a Kimi
    sandbox in mainland China gave up at about 20 MB of it, reports/055) one read timeout
    used to throw the whole download away with no retry at all. Now a failure keeps the
    bytes that arrived and asks for the rest with a Range header; a server that ignores the
    Range answers 200 and we start over. A short body with no error (the connection simply
    closed early) counts as a failure too, because gzip would only find out later.
    """
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        import time

        import httpx

        dest.unlink(missing_ok=True)
        got = 0
        for attempt in range(1, attempts + 1):
            headers = {"Range": f"bytes={got}-"} if got else {}
            total: int | None = None
            try:
                with httpx.stream("GET", url, follow_redirects=True, headers=headers,
                                  timeout=httpx.Timeout(60.0, connect=20.0)) as r:
                    if r.status_code == 206 and got:
                        mode = "ab"
                        rng = r.headers.get("content-range", "")
                        total = int(rng.rsplit("/", 1)[-1]) if rng.rsplit("/", 1)[-1].isdigit() else None
                    else:
                        r.raise_for_status()
                        mode, got = "wb", 0
                        cl = r.headers.get("content-length")
                        total = int(cl) if cl and cl.isdigit() else None
                    with open(dest, mode) as f:
                        for chunk in r.iter_bytes():
                            f.write(chunk)
                            got += len(chunk)
                if total is not None and got < total:
                    raise httpx.ReadError(f"connection closed after {got} of {total} bytes")
                return
            except httpx.HTTPStatusError:
                raise  # a 404 or 403 will not improve on retry; say what it was
            except (httpx.HTTPError, OSError):
                if attempt == attempts:
                    raise
                time.sleep(min(2.0 * attempt, 6.0))
    else:
        src = _local_path(url)
        if not src.exists():
            raise SnapshotError(f"snapshot not found at {src}")
        shutil.copyfile(src, dest)


def _validate_snapshot_db(db: Path) -> SnapshotInstallResult:
    """Refuse anything but a public-only snapshot: jobs present, every user-state table empty."""
    conn = sqlite3.connect(db)
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
        personal = _user_added_rows(conn)
        if personal:
            raise SnapshotError(
                f"downloaded snapshot is invalid: {personal} user-added employers (must be 0)."
            )
        data_as_of = _max_verified_at(conn)
    finally:
        conn.close()
    return SnapshotInstallResult(
        companies=companies, jobs=jobs, data_as_of=data_as_of, age_days=_age_days(data_as_of),
    )


def download_snapshot(url: str, dest_db: Path) -> SnapshotInstallResult:
    """Download, decompress and validate a snapshot into dest_db (never the live index path).

    dest_db is removed again if the file turns out not to be a valid public-only snapshot."""
    tmp_gz = _tempfile(".db.gz")
    try:
        _fetch_to(url, tmp_gz)
        with gzip.open(tmp_gz, "rb") as f_in, open(dest_db, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        try:
            return _validate_snapshot_db(dest_db)
        except Exception:
            dest_db.unlink(missing_ok=True)
            raise
    finally:
        tmp_gz.unlink(missing_ok=True)


def staged_path(db_path: str | Path) -> Path:
    """Where a downloaded snapshot waits until the next start activates it."""
    p = Path(db_path)
    return p.with_name(p.name + ".staged")


def stage_snapshot(url: str, db_path: str | Path) -> SnapshotInstallResult:
    """Download a snapshot next to the live index without touching the live file.

    The hosted endpoint uses this: a worker thread stages the new weekly snapshot while the
    server keeps answering from the old file, then the process restarts and `activate_staged`
    swaps the files before anything has them open. Overwriting a SQLite file that another
    thread is reading is how an index gets corrupted."""
    dest = staged_path(db_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        res = download_snapshot(url, tmp)
        os.replace(tmp, dest)
        return res
    finally:
        tmp.unlink(missing_ok=True)


def _sidecars(target: Path) -> tuple[Path, Path]:
    return target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")


def _checkpoint(db: Path) -> None:
    """Fold a WAL into its database so the file can be renamed without losing recent writes."""
    if not db.exists():
        return
    try:
        conn = sqlite3.connect(db)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def activate_staged(db_path: str | Path) -> Path | None:
    """Make a staged snapshot the live index. Returns the path of the previous index file
    (so its user state can be carried over with `carry_over_user_state`), or None when
    nothing was staged. Call this before anything opens the database."""
    target = Path(db_path)
    staged = staged_path(target)
    if not staged.exists():
        return None
    previous: Path | None = None
    if target.exists():
        _checkpoint(target)
        previous = target.with_name(target.name + ".previous")
        _replace(target, previous)
    for side in _sidecars(target):
        side.unlink(missing_ok=True)
    try:
        _replace(staged, target)
    except SnapshotError:
        if previous is not None:  # put the old index back rather than leave none at all
            os.replace(previous, target)
        raise
    return previous


def _replace(src: Path, dst: Path, attempts: int = 5, wait: float = 0.2) -> None:
    """os.replace with a short retry. On Windows a virus scanner or the search indexer can
    hold a file it just saw being written for a moment, and a file any program still has
    open cannot be renamed at all (WinError 32, 2026-10-15 on the maintainer's machine). A
    handle that is really open, such as Claude Desktop running openhire on the same index,
    does not go away by waiting; the error then names the likely holder."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:
            if attempt == attempts - 1:
                raise SnapshotError(
                    f"{src.name} is open in another program, so the index cannot be swapped ({exc}). "
                    "Stop whatever is using it, for example the openhire server inside Claude Desktop "
                    "(Settings > Developer), then run the command again."
                ) from exc
            time.sleep(wait)


def carry_over_user_state(old_db: str | Path, new_db: str | Path) -> dict[str, int]:
    """Copy the user-state tables (watches, application records) from the index being
    replaced into the new one. Rows are keyed by the client's anonymous fingerprint and
    carry no PII; losing them on every refresh is what made `ohp bootstrap --force` wipe a
    user's watches (roadmap item since 0.8.4). Shared columns only, so a snapshot built by a
    newer or older version still works; a table the new file lacks is created from the old
    file's own DDL. Returns rows copied per table."""
    old, new = Path(old_db), Path(new_db)
    if not old.exists() or not new.exists():
        return {}
    copied: dict[str, int] = {}
    conn = sqlite3.connect(new)
    try:
        conn.execute("ATTACH DATABASE ? AS old", (str(old),))
        for t in _USER_STATE_TABLES:
            row = conn.execute(
                "SELECT sql FROM old.sqlite_master WHERE type='table' AND name=?", (t,)
            ).fetchone()
            if not row:
                continue
            if not _table_exists(conn, t):
                conn.execute(row[0])
            dest_cols = [r[1] for r in conn.execute(f"PRAGMA main.table_info({t})").fetchall()]
            src_cols = {r[1] for r in conn.execute(f"PRAGMA old.table_info({t})").fetchall()}
            cols = [c for c in dest_cols if c in src_cols]
            if not cols:
                continue
            collist = ", ".join(cols)
            cur = conn.execute(f"INSERT OR IGNORE INTO main.{t} ({collist}) SELECT {collist} FROM old.{t}")
            copied[t] = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
        copied.update(_carry_over_user_employers(conn))
        conn.commit()
        conn.execute("DETACH DATABASE old")
    finally:
        conn.close()
    return copied


def _carry_over_user_employers(conn: sqlite3.Connection) -> dict[str, int]:
    """Employers the user added (companies.user_added = 1) and every posting of theirs move
    from the old index into the new one; the snapshot never carries them, so without this
    a refresh would silently drop the user's own radar. The new file may predate the
    column (a snapshot built by an older version): it is added here, before anything
    opens the index, the same way init_db's migration would."""
    if not (_table_exists(conn, "companies") and _table_exists(conn, "jobs")):
        return {}
    if not _has_column(conn, "companies", _USER_ADDED_COLUMN, "old"):
        return {}
    n = conn.execute(f"SELECT count(*) FROM old.companies WHERE {_USER_ADDED_COLUMN} = 1").fetchone()[0]
    if not n:
        return {}
    if not _has_column(conn, "companies", _USER_ADDED_COLUMN):
        conn.execute(f"ALTER TABLE main.companies ADD COLUMN {_USER_ADDED_COLUMN} BOOLEAN DEFAULT 0")
    out: dict[str, int] = {}
    for t, where in (
        ("companies", f"WHERE {_USER_ADDED_COLUMN} = 1"),
        ("jobs", f"WHERE company_id IN (SELECT id FROM old.companies WHERE {_USER_ADDED_COLUMN} = 1)"),
    ):
        dest_cols = [r[1] for r in conn.execute(f"PRAGMA main.table_info({t})").fetchall()]
        src_cols = {r[1] for r in conn.execute(f"PRAGMA old.table_info({t})").fetchall()}
        cols = [c for c in dest_cols if c in src_cols]
        if not cols:
            continue
        collist = ", ".join(cols)
        cur = conn.execute(f"INSERT OR IGNORE INTO main.{t} ({collist}) SELECT {collist} FROM old.{t} {where}")
        out[t] = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
    return out


def install_snapshot(url: str, db_path: str, preserve_user_state: bool = False) -> SnapshotInstallResult:
    """Download+decompress a snapshot into db_path. Verifies public-only content before
    installing (never write user-state). Overwrites db_path; with preserve_user_state the
    previous file's watches and application records are carried into the new index first.
    Callers must have released their own handles on db_path (dispose_engine)."""
    res = stage_snapshot(url, db_path)
    previous = activate_staged(db_path)
    if previous is not None:
        try:
            if preserve_user_state:
                carry_over_user_state(previous, db_path)
        finally:
            previous.unlink(missing_ok=True)
    return res


def snapshot_fingerprint(url: str) -> str | None:
    """Something that changes when the published snapshot does, without downloading it:
    ETag, length and last-modified from a HEAD (redirects followed), or size and mtime for a
    local path. None when the source cannot be asked right now."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        src = _local_path(url)
        try:
            st = src.stat()
        except OSError:
            return None
        return f"{st.st_size}:{int(st.st_mtime)}"
    import httpx

    try:
        r = httpx.head(url, follow_redirects=True, timeout=httpx.Timeout(30.0, connect=10.0))
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    parts = [r.headers.get(k, "") for k in ("etag", "content-length", "last-modified")]
    fp = "|".join(parts)
    return fp if any(parts) else None


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
