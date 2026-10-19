"""The user's own employers (0.8.13): any readable board goes into THIS machine's index on
request, behaves like a seeded employer, never enters a snapshot, and survives a refresh."""

from __future__ import annotations

import datetime as dt
import gzip
import sqlite3
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire import mcp_server, service
from openhire.ats import FetchResult, JobRecord
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 15, tzinfo=UTC)


@contextmanager
def _db(path):
    """sqlite3's own `with` commits but never closes, and Windows will not rename or delete
    a file that still has an open handle (WinError 32): every connection here is closed."""
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _board(n=2, ok=True):
    recs = [JobRecord(ats_job_id=f"j{i}", title=f"Partner Manager {i}", description_raw="Partnerships, Hong Kong, APAC",
                      apply_channel=f"https://jobs.ashbyhq.com/uipath/j{i}", location="Hong Kong",
                      posted_at=NOW - dt.timedelta(days=i)) for i in range(1, n + 1)]
    return lambda vendor, tenant: FetchResult(ok=ok, status=200 if ok else 503, records=recs if ok else [], error=None if ok else "timeout")


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="mongodb", name="MongoDB", ats_vendor="greenhouse", ats_tenant="mongodb",
                      careers_url="https://boards.greenhouse.io/mongodb", last_crawled_at=NOW))
        s.commit()
        yield s
    engine.dispose()


def test_add_crawls_once_and_the_employer_behaves_like_a_seeded_one(session):
    res = service.add_employer(session, "https://jobs.ashbyhq.com/uipath", name="UiPath", now=NOW, fetch=_board())
    assert res["added"] and res["company_id"] == "uipath" and res["jobs_indexed"] == 2 and res["user_added"]
    assert res["suggest_for_public_index"].startswith("https://github.com/gzchenhao/openhire/issues/new?title=")
    c = session.get(Company, "uipath")
    assert c.user_added is True and c.name == "UiPath" and c.ats_vendor == "ashby"
    jobs = session.execute(select(Job).where(Job.company_id == "uipath")).scalars().all()
    assert len(jobs) == 2 and all(j.posted_at is not None for j in jobs)
    info = service.get_company_info(session, "uipath", now=NOW)
    assert info["user_added"] is True and info["active_jobs"] == 2
    # Searchable by name like any employer:
    assert [x.id for x in service.resolve_company(session, "UiPath")] == ["uipath"]


def test_adding_twice_or_a_seeded_employer_says_already_in_index(session):
    service.add_employer(session, "https://jobs.ashbyhq.com/uipath", now=NOW, fetch=_board())
    again = service.add_employer(session, "https://jobs.ashbyhq.com/uipath/some-job", now=NOW, fetch=_board())
    assert again["added"] is False and again["reason"] == "already_in_index" and again["user_added"] is True
    seeded = service.add_employer(session, "https://boards.greenhouse.io/mongodb", now=NOW, fetch=_board())
    assert seeded["added"] is False and seeded["company_id"] == "mongodb" and seeded["user_added"] is False


def test_a_board_that_does_not_answer_adds_nothing(session):
    with pytest.raises(OpenHireError) as ei:
        service.add_employer(session, "https://jobs.lever.co/lalamove", now=NOW, fetch=_board(ok=False))
    assert ei.value.code == "ERR_BOARD_UNREADABLE"
    assert session.execute(select(Company).where(Company.ats_tenant == "lalamove")).first() is None


def test_closed_portals_are_refused_like_read_board(session):
    with pytest.raises(OpenHireError) as ei:
        service.add_employer(session, "https://ponyai.jobs.feishu.cn/ponyai/", now=NOW, fetch=_board())
    assert ei.value.code == "ERR_UNSUPPORTED_BOARD" and "closed_portal" in ei.value.message


def test_id_collision_with_another_vendor_gets_a_prefixed_id(session):
    session.add(Company(id="uipath", name="Other UiPath", ats_vendor="lever", ats_tenant="uipath-x",
                        careers_url="x", last_crawled_at=NOW))
    session.flush()
    res = service.add_employer(session, "https://jobs.ashbyhq.com/uipath", now=NOW, fetch=_board())
    assert res["added"] and res["company_id"] == "ashby-uipath"


def test_remove_takes_out_only_user_added_employers(session):
    service.add_employer(session, "https://jobs.ashbyhq.com/uipath", now=NOW, fetch=_board())
    with pytest.raises(OpenHireError) as ei:
        service.remove_employer(session, "mongodb")
    assert ei.value.code == "ERR_NOT_USER_ADDED"
    res = service.remove_employer(session, "uipath")
    assert res["removed"] and res["jobs_removed"] == 2
    assert session.get(Company, "uipath") is None
    assert session.execute(select(Job).where(Job.company_id == "uipath")).first() is None
    with pytest.raises(OpenHireError):
        service.remove_employer(session, "uipath")


def test_read_board_offers_the_next_step_for_an_unindexed_employer(session):
    res = service.read_board(session, "https://jobs.ashbyhq.com/uipath", now=NOW, fetch=_board())
    assert "add_employer" in res["add_to_my_index"]
    assert res["suggest_for_public_index"].startswith("https://github.com/gzchenhao/openhire/issues/new?")
    indexed = service.read_board(session, "https://boards.greenhouse.io/mongodb", now=NOW, fetch=_board())
    assert "add_to_my_index" not in indexed


# --- snapshots: never published, always carried over -------------------------------------
def _db_with_user_employer(path):
    engine = create_engine(f"sqlite+pysqlite:///{path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=NOW))
        s.add(Job(id="acme:1", company_id="acme", title="Rust Infra", description_raw="x", skills=["rust"],
                  remote_policy="remote", first_seen_at=NOW, verified_at=NOW, source="ats_public_api",
                  ghost_score=0.0, role_family="engineering",
                  apply_channel="https://boards.greenhouse.io/embed/job_app?for=acme&token=1", content_hash="h1"))
        s.commit()
        service.add_employer(s, "https://jobs.ashbyhq.com/uipath", name="UiPath", now=NOW, fetch=_board())
        s.commit()
    engine.dispose()


def test_snapshot_build_leaves_user_added_employers_out(tmp_path):
    from openhire.pipeline.snapshot import SnapshotError, _validate_snapshot_db, build_snapshot

    src = tmp_path / "src.db"
    _db_with_user_employer(src)
    gz = tmp_path / "snap.db.gz"
    res = build_snapshot(str(src), str(gz))
    assert res.companies == 1 and res.jobs == 1   # acme only; UiPath and its 2 postings stayed home
    raw = tmp_path / "snap.db"
    with gzip.open(gz, "rb") as f_in, open(raw, "wb") as f_out:
        f_out.write(f_in.read())
    with _db(raw) as c:
        assert c.execute("SELECT count(*) FROM companies WHERE user_added = 1").fetchone()[0] == 0
    # And a snapshot that somehow carries one is refused on install:
    with _db(raw) as c:
        c.execute("UPDATE companies SET user_added = 1")
    with pytest.raises(SnapshotError):
        _validate_snapshot_db(raw)


def test_refresh_carries_the_users_employers_into_the_new_index(tmp_path):
    from openhire.pipeline.snapshot import activate_staged, carry_over_user_state, stage_snapshot

    live = tmp_path / "openhire.db"
    _db_with_user_employer(live)
    # A public snapshot built by an older version: one seeded employer, and no user_added
    # column at all (dropped below), which is what every snapshot published before 0.8.13 looks like.
    pub = tmp_path / "pub.db"
    engine = create_engine(f"sqlite+pysqlite:///{pub.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=NOW))
        s.add(Job(id="acme:2", company_id="acme", title="New Role", description_raw="x", skills=["rust"],
                  remote_policy="remote", first_seen_at=NOW, verified_at=NOW, source="ats_public_api",
                  ghost_score=0.0, role_family="engineering",
                  apply_channel="https://boards.greenhouse.io/embed/job_app?for=acme&token=2", content_hash="h2"))
        s.commit()
    engine.dispose()
    with _db(pub) as c:
        try:
            c.execute("ALTER TABLE companies DROP COLUMN user_added")
        except sqlite3.OperationalError:
            pass  # an old SQLite cannot drop a column; the carry-over still has to work
        c.execute("DROP TABLE IF EXISTS watches")
        c.execute("DROP TABLE IF EXISTS applications")
    gz = tmp_path / "pub.db.gz"
    with open(pub, "rb") as f_in, gzip.open(gz, "wb") as f_out:
        f_out.write(f_in.read())

    stage_snapshot(gz.as_uri(), live)
    previous = activate_staged(live)
    copied = carry_over_user_state(previous, live)
    assert copied["companies"] == 1 and copied["jobs"] == 2
    with _db(live) as c:
        assert c.execute("SELECT user_added FROM companies WHERE id='uipath'").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM jobs WHERE company_id='uipath'").fetchone()[0] == 2
        assert [r[0] for r in c.execute("SELECT id FROM jobs WHERE company_id='acme'")] == ["acme:2"]   # the new snapshot's


def test_tools_are_registered_with_honest_annotations():
    tools = {t.name: t for t in mcp_server.mcp._tool_manager.list_tools()}
    add, rm = tools["add_employer"], tools["remove_employer"]
    assert add.annotations.readOnlyHint is False and add.annotations.openWorldHint is True
    assert rm.annotations.destructiveHint is True and rm.annotations.openWorldHint is False
    assert "never part of the public snapshot" in " ".join(add.description.split())
    assert "Workday" in tools["read_board"].description
