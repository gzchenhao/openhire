"""One-off data repair: skill tags on postings that never had a description.

Until 2026-09-23 the extractors mined skills from `title + description_raw`, so a posting
whose employer gave us no JD at all (a first-party roster row whose detail call failed,
or a source that publishes none) could carry tags read off the title alone: "Python 工程师"
became `["python"]`, and an LLM handed a bare title answered from what the title implied.
A tag is a claim that the employer asked for that skill, and a bare title cannot support
it. The extractors now emit no skills without a JD; this repairs the rows written before.

Where trim(description_raw) is empty and skills is non-empty:
  * skills            -> []
  * extraction_source -> 'heuristic'  (the LLM did not read a JD here, so it does not
                         get to sign the row; the monthly LLM pass skips empty JDs anyway)

Delisted rows are repaired too: a relist would revive the wrong tags otherwise.

Usage:  python scripts/clean_empty_jd.py <sqlite file> [--apply]
Without --apply it only reports. Safe to re-run.
"""
from __future__ import annotations

import json
import sqlite3
import sys


def find_rows(conn: sqlite3.Connection) -> list[tuple[str, str | None, str | None, bool]]:
    """(id, extraction_source, skills_json, is_live) for every row that needs repair."""
    rows = conn.execute(
        "select id, extraction_source, skills, delisted_at is null"
        " from jobs"
        " where length(trim(coalesce(description_raw, ''), ' \t\r\n')) = 0"
    ).fetchall()
    out = []
    for jid, src, sk, live in rows:
        stored = json.loads(sk) if sk else []
        if stored:
            out.append((jid, src, sk, bool(live)))
    return out


def main(path: str, apply: bool) -> int:
    conn = sqlite3.connect(path)
    try:
        rows = find_rows(conn)
        live = sum(1 for r in rows if r[3])
        by_source: dict[str, int] = {}
        for _, src, _, _ in rows:
            by_source[src or "null"] = by_source.get(src or "null", 0) + 1
        print(
            f"rows with an empty JD and non-empty skills: {len(rows)} "
            f"(live: {live}, delisted: {len(rows) - live}) | by extraction_source: "
            + (", ".join(f"{k}={v}" for k, v in sorted(by_source.items())) or "none")
        )
        if apply and rows:
            conn.executemany(
                "update jobs set skills = '[]', extraction_source = 'heuristic' where id = ?",
                [(jid,) for jid, _, _, _ in rows],
            )
            conn.commit()
            print(f"applied: {len(rows)} rows now carry no skills and are stamped heuristic")
        elif rows:
            print("dry run: nothing written (pass --apply to repair)")
        return len(rows)
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], "--apply" in sys.argv)
