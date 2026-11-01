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

LANG = ('.lang-en{display:none}\nhtml[data-lang="en"] .lang-zh{display:none}\n'
        'html[data-lang="en"] .lang-en{display:block}')
SWITCH = ".switch{display:flex;justify-content:flex-end;gap:8px;margin:0 0 16px}"

EXTRA = {
    "index": "main>ul{padding-left:1.1em}\nmain>ul>li{margin:12px 0}",
    "employers": "",
    "checklist": "\n".join([
        ".tag{display:inline-block;font-size:11px;padding:0 6px;border:1px solid var(--border);border-radius:4px;"
        "color:var(--fg-dim);background:var(--bg2);margin-right:4px}",
        SWITCH, LANG]),
    "connect": "\n".join([
        SWITCH,
        ".pick{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 20px}",
        ".client{background:var(--bg2);border-left:3px solid var(--accent);border-radius:0 4px 4px 0;"
        "box-shadow:0 1px 3px rgba(0,0,0,.06);padding:4px 18px 16px;margin:16px 0}",
        ".client pre{background:var(--bg);box-shadow:none}",
        ".client h2{border-left:none;padding-left:0;margin-top:16px}",
        "html[data-picked] .client{display:none}",
        'html[data-picked] .client[data-show="1"]{display:block}',
        ".copy{position:absolute;top:8px;right:8px;padding:0 8px}",
        ".os-win,.os-mac{display:inline}",
        'html[data-os="mac"] .os-win{display:none}',
        'html[data-os="win"] .os-mac{display:none}',
        LANG]),
}
PAGES = {"index": "index.html", "employers": "employers.html", "checklist": "checklist.html", "connect": "connect.html"}
PACKAGED = ("checklist", "connect")


def style_block(key: str) -> str:
    extra = EXTRA[key]
    return "<style>\n" + house_style.CSS + ("\n" + extra if extra else "") + "\n</style>"


def apply(page: str, key: str) -> str:
    page = re.sub(r"<style>.*?</style>", lambda _m: style_block(key), page, count=1, flags=re.S)
    bar = house_style.nav(key)
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
