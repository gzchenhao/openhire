"""Live postings first published inside a recent window, per employer, from a snapshot.

Why (reports/082): a reader on Zhihu (善水, 2026-10-09) pointed out that "how many postings
are live" mixes long-open roles with fresh ones, and asked for the postings published in
the last 30 days instead. This counts exactly that, for the same 37 embodied-AI employers
the 2026-10-14 JD scan used (scripts/jd_signal_scan.py), so the two numbers line up.

Only rows whose source reports a posting date count as "new": a row without one (its date
is the day the index first saw it, date_signal not_reported_by_ats) is reported separately
and never counted as new. Rows published and already closed inside the window are not
counted either: this is "live now and first published in the window".

    python scripts/new_postings_window.py --db openhire-index.db --days 30 [--json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jd_signal_scan import EMBODIED, EMBODIED_CN, EMBODIED_OVERSEAS  # noqa: E402


def count(db_path: str, days: int = 30) -> dict:
    con = sqlite3.connect(db_path)
    try:
        snap = con.execute("select max(verified_at) from jobs").fetchone()[0]
        end = dt.date.fromisoformat(str(snap)[:10])
        start = end - dt.timedelta(days=days)
        q = ("select j.company_id, c.name, j.posted_at from jobs j join companies c on c.id = j.company_id "
             "where j.delisted_at is null and j.company_id in (%s)" % ",".join("?" * len(EMBODIED)))
        live: dict[str, int] = defaultdict(int)
        new: dict[str, int] = defaultdict(int)
        undated: dict[str, int] = defaultdict(int)
        names: dict[str, str] = {}
        for cid, name, posted in con.execute(q, EMBODIED):
            names[cid] = name
            live[cid] += 1
            if posted is None:
                undated[cid] += 1
            elif start < dt.date.fromisoformat(str(posted)[:10]) <= end:
                new[cid] += 1
    finally:
        con.close()

    def region(ids: list[str]) -> dict:
        rows = sorted((cid for cid in ids if live[cid]), key=lambda c: (-new[c], names[c]))
        return {
            "employers_with_live_postings": len(rows),
            "live": sum(live[c] for c in rows),
            "new_in_window": sum(new[c] for c in rows),
            "undated": sum(undated[c] for c in rows),
            "by_employer": [{"company_id": c, "name": names[c], "live": live[c], "new_in_window": new[c],
                             "undated": undated[c]} for c in rows],
        }

    return {
        "snapshot_verified_at": str(snap),
        "window_days": days,
        "window": [start.isoformat(), end.isoformat()],
        "definition": ("live postings whose employer-reported posting date falls in (start, end]; "
                       "rows without a reported date are counted as undated, never as new"),
        "cn": region(EMBODIED_CN),
        "overseas": region(EMBODIED_OVERSEAS),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = count(a.db, a.days)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"snapshot {out['snapshot_verified_at']}  window {out['window'][0]} .. {out['window'][1]}")
    for key in ("cn", "overseas"):
        r = out[key]
        print(f"{key}: {r['employers_with_live_postings']} employers, live {r['live']}, "
              f"new in {a.days} days {r['new_in_window']}, undated {r['undated']}")
        for e in r["by_employer"]:
            print(f"  {e['name']:<28} live {e['live']:>4}  new {e['new_in_window']:>3}  undated {e['undated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
