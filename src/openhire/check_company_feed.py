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
