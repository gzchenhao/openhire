"""One-off data repair for the skill-tag noise found on 2026-09-23 (reports/052).

Two things were wrong in the stored data:

1. Vocabulary tags with no textual basis: the shared regex vocabulary matched `rust` inside
   "trust" and `scala` inside "scalable". Any vocabulary tag whose (now word-bounded)
   patterns match nowhere in the posting text is removed, whichever extractor wrote it.
2. Heuristic skill lists wearing an LLM stamp: the weekly re-crawl overwrote skills with
   the heuristic extractor on changed postings without moving `extraction_source`. A row
   whose stored list equals the OLD heuristic output exactly is re-tagged with the fixed
   heuristic and stamped `heuristic`, so the next monthly LLM pass picks it up again.

Usage:  python scripts/clean_skill_noise.py <sqlite file> [--apply]
Without --apply it only reports. Safe to re-run.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys

from openhire.pipeline.extract import _SKILL_VOCAB, extract_skills

# The pre-0.6.4 matcher, reconstructed: the same patterns without the boundary wrapper.
_OLD = {tag: [re.compile(p, re.I) for p in pats] for tag, pats in _SKILL_VOCAB.items()}


def _old_extract(text: str, limit: int = 12) -> list[str]:
    found = [tag for tag, pats in _OLD.items() if any(p.search(text) for p in pats)]
    return found[:limit]


def _has_evidence(tag: str, text: str) -> bool:
    pats = _SKILL_VOCAB.get(tag)
    if pats is None:
        return True  # not a vocabulary tag: an LLM judgement we do not second-guess here
    return any(re.search(rf"(?<![a-z0-9]){p}(?![a-z0-9])" if "\\b" not in p else p, text, re.I) for p in pats)


def main(path: str, apply: bool) -> None:
    c = sqlite3.connect(path)
    rows = c.execute(
        "select id, extraction_source, title, description_raw, skills from jobs where delisted_at is null"
    ).fetchall()
    restamped = stripped_rows = stripped_tags = 0
    updates: list[tuple[str, str, str]] = []
    for jid, src, title, desc, sk in rows:
        stored = json.loads(sk) if sk else []
        if not stored:
            continue
        text = f"{title or ''}\n{desc or ''}"
        if stored == _old_extract(text) and src != "heuristic":
            new_skills, new_src = extract_skills(text), "heuristic"
            restamped += 1
        else:
            new_skills = [t for t in stored if _has_evidence(t, text)]
            new_src = src
            if len(new_skills) != len(stored):
                stripped_rows += 1
                stripped_tags += len(stored) - len(new_skills)
        if new_skills != stored or new_src != src:
            updates.append((json.dumps(new_skills, ensure_ascii=False), new_src, jid))
    print(f"live rows: {len(rows)} | re-stamped heuristic: {restamped} | "
          f"rows with evidence-less vocab tags stripped: {stripped_rows} (tags: {stripped_tags}) | "
          f"updates: {len(updates)}")
    if apply and updates:
        c.executemany("update jobs set skills=?, extraction_source=? where id=?", updates)
        c.commit()
        print("applied")
    c.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], "--apply" in sys.argv)
