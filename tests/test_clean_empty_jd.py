"""scripts/clean_empty_jd.py: the one-off repair for skills mined from a bare title.

Runs against a throwaway SQLite file built from the real models, never against the
maintainer's database.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire.db.models import Base, Company, Job

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 23, tzinfo=UTC)
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "clean_empty_jd.py"


def _load():
    spec = importlib.util.spec_from_file_location("clean_empty_jd", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _job(jid, desc, skills, source, delisted=None):
    return Job(
        id=jid, company_id="acme", title="Python 工程师", description_raw=desc, skills=skills,
        remote_policy="unknown", first_seen_at=NOW, verified_at=NOW, delisted_at=delisted,
        source="ats_public_api", apply_channel="https://boards.greenhouse.io/acme/jobs/1",
        content_hash=f"h{jid}", ghost_score=0.0, extraction_source=source,
    )


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "repair.db"
    engine = create_engine(f"sqlite+pysqlite:///{path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=NOW))
        s.add(_job("acme:bare", "", ["python"], "deepseek"))           # the bug
        s.add(_job("acme:blank", "  \n\t", ["python", "go"], "heuristic"))  # whitespace is empty
        s.add(_job("acme:gone", "", ["python"], "glm", delisted=NOW))  # delisted: repaired too
        s.add(_job("acme:clean", "", [], "heuristic"))                 # already right
        s.add(_job("acme:jd", "熟悉 Python。", ["python"], "deepseek"))  # has a JD: untouched
        s.commit()
    engine.dispose()
    return path


def _state(path):
    c = sqlite3.connect(path)
    try:
        return {
            jid: (json.loads(sk) if sk else [], src)
            for jid, sk, src in c.execute("select id, skills, extraction_source from jobs")
        }
    finally:
        c.close()


def test_dry_run_reports_and_writes_nothing(db, capsys):
    before = _state(db)
    n = _load().main(str(db), apply=False)
    assert n == 3
    out = capsys.readouterr().out
    assert "empty JD and non-empty skills: 3" in out and "dry run" in out
    assert "live: 2, delisted: 1" in out
    assert _state(db) == before


def test_apply_clears_skills_and_restamps_heuristic(db):
    n = _load().main(str(db), apply=True)
    assert n == 3
    after = _state(db)
    for jid in ("acme:bare", "acme:blank", "acme:gone"):
        assert after[jid] == ([], "heuristic"), jid
    assert after["acme:clean"] == ([], "heuristic")
    assert after["acme:jd"] == (["python"], "deepseek")
    # Idempotent: a second run finds nothing.
    assert _load().main(str(db), apply=True) == 0
