"""scripts/new_postings_window.py: the weekly "new this week" table (reports/082, 084).

Pinned: only live rows whose employer-reported date falls inside the window count as new;
undated rows are reported apart and never counted; the --list option carries the postings."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "new_postings_window.py"


def _load():
    spec = importlib.util.spec_from_file_location("new_postings_window", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_window_counts_only_dated_live_rows_inside_it(tmp_path):
    db = tmp_path / "snap.db"
    con = sqlite3.connect(db)
    try:
        con.execute("create table companies (id text primary key, name text)")
        con.execute("create table jobs (id text, company_id text, title text, location text, apply_channel text, "
                    "posted_at text, verified_at text, delisted_at text)")
        con.execute("insert into companies values ('unitree', '宇树科技 Unitree'), ('1x', '1X Technologies')")
        rows = [
            ("u1", "unitree", "感知算法", "杭州", "https://a/1", "2026-10-18 09:00:00", "2026-10-19 13:00:00", None),
            ("u2", "unitree", "老岗位", "杭州", "https://a/2", "2026-09-01 09:00:00", "2026-10-19 13:00:00", None),
            ("u3", "unitree", "已下架", "杭州", "https://a/3", "2026-10-17 09:00:00", "2026-10-19 13:00:00", "2026-10-18"),
            ("u4", "unitree", "无日期", "杭州", "https://a/4", None, "2026-10-19 13:00:00", None),
            ("x1", "1x", "Engineer", "Palo Alto", "https://b/1", "2026-10-13 00:00:00", "2026-10-19 13:00:00", None),
        ]
        con.executemany("insert into jobs values (?,?,?,?,?,?,?,?)", rows)
        con.commit()
    finally:
        con.close()
    out = _load().count(str(db), days=7, with_list=True)
    assert out["window"] == ["2026-10-12", "2026-10-19"]
    cn, ov = out["cn"], out["overseas"]
    assert (cn["live"], cn["new_in_window"], cn["undated"]) == (3, 1, 1)
    assert [p["title"] for p in cn["by_employer"][0]["new_postings"]] == ["感知算法"]
    assert (ov["live"], ov["new_in_window"]) == (1, 1)
    assert "new_postings" not in _load().count(str(db), days=7)["cn"]["by_employer"][0]
