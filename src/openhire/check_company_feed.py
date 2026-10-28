"""The 查公司 page as a feed another site renders in its own template.

Why: EarlyTip shows 查公司 as a column of its own (like its 顶会归档) and wants it to follow
this page without anyone telling it when the page changed (the maintainer, 2026-10-27,
reports/095). A link or an iframe would hand EarlyTip's readers to github.io, which is often
unreachable from mainland China. So the page is also published as JSON: EarlyTip's own job
fetches it on a schedule, compares `sha256`, and re-renders when it moved.

The `html` field is rebuilt here from the page body between the title and the footer rule,
keeping only a handful of tags and only https `href`s, every text node escaped. What EarlyTip
receives is therefore safe to render by construction; it still sanitizes on its side.

The same file is published three ways: docs/check-company.json on github.io (live minutes
after a push to main), the hosted endpoint's /check-company.json (live on each release), and
the CNB code mirror (synced every six hours). tests/test_check_company_feed.py keeps the docs
copy equal to what `build` makes from docs/check-company.html.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser

SCHEMA = 1
ALLOWED_TAGS = ("h2", "p", "ul", "li", "table", "tr", "th", "td", "a")
SOURCES = (
    "https://gzchenhao.github.io/openhire/check-company.json",
    "https://openhire-vlny.onrender.com/check-company.json",
    "https://cnb.cool/gzchenhao/openhire/-/git/raw/main/docs/check-company.json",
)
PAGE_URL = "https://gzchenhao.github.io/openhire/check-company.html"
PAGE_URL_CN = "https://openhire-vlny.onrender.com/check-company"
FEEDBACK_URL = "https://github.com/gzchenhao/openhire/issues"


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.anchors: list[bool] = []  # per open <a>: was it kept?
        self.skipping = 0  # inside <script> / <style>: drop the text too

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skipping += 1
        if tag not in ALLOWED_TAGS:
            return
        if tag == "a":
            href = dict(attrs).get("href") or ""
            self.anchors.append(href.startswith("https://"))
            if not self.anchors[-1]:
                return
            self.out.append(f'<a href="{html.escape(href, quote=True)}">')
        else:
            self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skipping = max(0, self.skipping - 1)
        if tag == "a" and not (self.anchors.pop() if self.anchors else False):
            return
        if tag in ALLOWED_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skipping:
            return
        self.out.append(html.escape(data, quote=False))


def build(page: str) -> dict:
    """The feed for one version of docs/check-company.html."""
    title = re.search(r"<h1>(.*?)</h1>", page, re.S).group(1).strip()
    body = page.split("</h1>", 1)[1].split("<hr>", 1)[0]
    sanitizer = _Sanitizer()
    sanitizer.feed(body)
    sanitizer.close()
    fragment = re.sub(r"\n{2,}", "\n", "".join(sanitizer.out)).strip() + "\n"
    updated = re.search(r"最后更新 (\d{4}-\d{2}-\d{2})", page).group(1)
    return {
        "schema": SCHEMA,
        "title": title,
        "updated": updated,
        "sha256": hashlib.sha256(fragment.encode("utf-8")).hexdigest(),
        "page_url": PAGE_URL,
        "page_url_cn": PAGE_URL_CN,
        "feedback_url": FEEDBACK_URL,
        "sources": list(SOURCES),
        "allowed_tags": list(ALLOWED_TAGS),
        "html": fragment,
    }


def dumps(feed: dict) -> str:
    return json.dumps(feed, ensure_ascii=False, indent=2) + "\n"


# EarlyTip renders this feed as its own 查公司 column and runs two gates of its own before it
# replaces what it shows (its project manager, 2026-10-28, column live at
# earlytip.com/check-company.html): the visible text must not contain any of these words
# (case-insensitive; "mcp" anywhere, not only "/mcp", and the product name included), and
# the new text must not be shorter than half of the previous one. A feed that fails either
# is never shown there, and EarlyTip gets an alert instead. The same two gates run here, in
# the tests and in scripts/build_check_company_feed.py, so a page EarlyTip would refuse is
# never published in the first place; a deliberate shrink past the half mark is told to
# EarlyTip before it goes out (the build script needs --allow-shrink for it).
EARLYTIP_BANNED_WORDS = ("求职", "招聘", "岗位", "mcp", "安装", "openhire")
EARLYTIP_MIN_RATIO = 0.5


def visible_text(fragment: str) -> str:
    """What a reader sees of an HTML fragment: tags dropped, entities decoded."""
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment))


def earlytip_gate(feed: dict, previous: dict | None = None) -> list[str]:
    """The problems EarlyTip's own gates would raise on `feed`; empty when it would be shown.

    `previous` is the feed EarlyTip currently shows (for us: the docs copy before this
    rebuild); without it only the word gate runs."""
    low = visible_text(feed.get("html", "")).lower()
    problems = [f"visible text contains {w!r}, which EarlyTip refuses" for w in EARLYTIP_BANNED_WORDS if w in low]
    before = len((previous or {}).get("html", "")) if previous else 0
    after = len(feed.get("html", ""))
    if before and after < before * EARLYTIP_MIN_RATIO:
        problems.append(
            f"html shrank from {before} to {after} characters, past EarlyTip's half-length gate: "
            "it would keep showing the old version and raise an alert there"
        )
    return problems
