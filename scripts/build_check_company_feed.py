"""Regenerate docs/check-company.json from docs/check-company.html.

Run after every edit to the 查公司 page (and copy the page to src/openhire/pages/ as
before); tests/test_check_company_feed.py fails until the two agree. EarlyTip renders this
feed as its own 查公司 column (reports/095).

    python scripts/build_check_company_feed.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openhire.check_company_feed import build, dumps  # noqa: E402

page = (ROOT / "docs" / "check-company.html").read_text(encoding="utf-8")
out = ROOT / "docs" / "check-company.json"
out.write_text(dumps(build(page)), encoding="utf-8", newline="\n")
print(f"wrote {out.relative_to(ROOT)}")
