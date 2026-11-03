"""Write the house style (src/openhire/house_style.py) into the static pages.

Each page's first <style> block becomes house_style.CSS plus that page's own few rules (the
language switch, the connect guide's picker and copy buttons), the top bar is put right after
<body>, and the body is wrapped in <main>. Running it again rewrites the same bytes. The
packaged twins of checklist.html and connect.html are copied from docs/ afterwards, because
tests pin each pair byte for byte.

    python scripts/apply_house_style.py
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openhire import house_style  # noqa: E402


EXTRA = {
    "index": "",
    "employers": "",
    "checklist": "\n".join([
        ".tag{display:inline-block;font-size:11px;padding:0 6px;border:1px solid var(--border);border-radius:4px;"
        "color:var(--fg-dim);background:var(--bg2);margin-right:4px}",
        ]),
    "connect": "\n".join([
        ".pick{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 20px}",
        ".client{border-bottom:1px solid var(--border);padding:0 0 12px;margin:0 0 8px}",
        ".client h2{font-size:13px;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px;margin:18px 0 8px;line-height:1.7}",
        ".client h2::before{content:none;counter-increment:none}",
        "html[data-picked] .client{display:none}",
        'html[data-picked] .client[data-show="1"]{display:block}',
        ".copy{position:absolute;top:8px;right:8px;padding:0 8px}",
        ".os-win,.os-mac{display:inline}",
        'html[data-os="mac"] .os-win{display:none}',
        'html[data-os="win"] .os-mac{display:none}',
        ]),
}
PAGE_DATE = "2026-11-03"  # last content change; bump it when a page's text changes
PAGES = {"index": "index.html", "employers": "employers.html", "checklist": "checklist.html", "connect": "connect.html"}
PACKAGED = ("checklist", "connect")


def style_block(key: str) -> str:
    extra = EXTRA[key]
    return "<style>\n" + house_style.CSS + ("\n" + extra if extra else "") + "\n</style>"


def apply(page: str, key: str) -> str:
    page = re.sub(r"<style>.*?</style>", lambda _m: style_block(key), page, count=1, flags=re.S)
    bar = house_style.nav(key, switch=True)
    # The language switch lives in the top bar now (reports/134); drop the old one in <main>.
    page = re.sub(r'<div class="switch"[^>]*>.*?</div>\n', "", page, flags=re.S)
    # EarlyTip's daily brief opens with a date line above the title.
    page = re.sub(r'(?<!</p>\n)<h1>', f'<p class="page-date">{PAGE_DATE}</p>\n<h1>', page)
    if '<nav class="house"' in page:
        page = re.sub(r'<nav class="house".*?</nav>', lambda _m: bar, page, count=1, flags=re.S)
    else:
        page = page.replace("<body>\n", f"<body>\n{bar}\n<main>\n", 1)
        page = page.replace("\n</body>", "\n</main>\n</body>", 1)
    return page


def main() -> int:
    for key, name in PAGES.items():
        path = ROOT / "docs" / name
        before = path.read_text(encoding="utf-8")
        after = apply(before, key)
        path.write_text(after, encoding="utf-8")
        print(f"{name}: {'rewritten' if after != before else 'unchanged'}")
        if key in PACKAGED:
            shutil.copyfile(path, ROOT / "src" / "openhire" / "pages" / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
