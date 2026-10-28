"""Regenerate docs/check-company.json from docs/check-company.html.

Run after every edit to the 查公司 page (and copy the page to src/openhire/pages/ as
before); tests/test_check_company_feed.py fails until the two agree. EarlyTip renders this
feed as its own 查公司 column (reports/095) and applies two gates before showing a new
version (reports/099): no 求职 / 招聘 / 岗位 / mcp / 安装 / OpenHire in the visible text,
and no shrink past half of the previous length. Both run here first: a page that fails the
word gate is refused outright; a shrink past the half mark is refused unless --allow-shrink
is given, which is the step for a change that has been announced to EarlyTip beforehand.

    python scripts/build_check_company_feed.py [--allow-shrink]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openhire.check_company_feed import build, dumps, earlytip_gate  # noqa: E402


def main(root: Path = ROOT, allow_shrink: bool = False) -> int:
    page = (root / "docs" / "check-company.html").read_text(encoding="utf-8")
    out = root / "docs" / "check-company.json"
    previous = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    feed = build(page)
    problems = earlytip_gate(feed, previous)
    if allow_shrink:
        problems = [p for p in problems if "shrank" not in p]
    if problems:
        print("refused, nothing written:")
        for p in problems:
            print(f"  - {p}")
        return 1
    out.write_text(dumps(feed), encoding="utf-8", newline="\n")
    before = len(previous["html"]) if previous and previous.get("html") else None
    size = f"{before} -> {len(feed['html'])}" if before is not None and before != len(feed["html"]) else str(len(feed["html"]))
    print(f"wrote {out.relative_to(root)} · html {size} chars · updated {feed['updated']} · sha256 {feed['sha256']}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--allow-shrink", action="store_true",
                    help="publish a page shorter than half of the previous feed (tell EarlyTip first)")
    sys.exit(main(allow_shrink=ap.parse_args().allow_shrink))
