"""Open every external link on the public checklist pages and report the ones that are gone.

Usage: python3 scripts/check_page_links.py docs/checklist.html docs/check-company.html

The pages send job seekers to official registers and anti-fraud services; an address that
has moved sends them nowhere. A monthly workflow (.github/workflows/check-links.yml) runs
this and mails the maintainer when a link answers 404 or 410. A timeout or a connection
error is reported as "unreachable from this runner" and does not fail the run: several of
these sites block data-centre addresses, which says nothing about the address itself.
Standard library only.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request

GONE = {404, 410}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; openhire-link-check; +https://github.com/gzchenhao/openhire)",
           "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}


def links(path: str) -> list[str]:
    text = open(path, encoding="utf-8").read()
    out = []
    for href in re.findall(r'href="(https?://[^"]+)"', text):
        if "github.com/gzchenhao/openhire" in href or href not in out:
            out.append(href)
    return [h for h in out if "github.com/gzchenhao/openhire" not in h]


def probe(url: str) -> tuple[str, int | None, str]:
    """('ok' | 'gone' | 'unreachable', status, detail)."""
    last = ""
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=HEADERS, method="GET")
            with urllib.request.urlopen(req, timeout=40) as r:
                return "ok", r.status, ""
        except urllib.error.HTTPError as e:
            if e.code in GONE:
                return "gone", e.code, str(e)
            return "ok", e.code, f"answered {e.code} (the address exists)"
        except Exception as e:  # timeouts, TLS, refused: the runner, not the address
            last = f"{type(e).__name__}: {e}"
    return "unreachable", None, last


def main(paths: list[str]) -> int:
    gone = []
    for path in paths:
        for url in links(path):
            state, status, detail = probe(url)
            print(f"{state:<12} {status if status is not None else '-':>4}  {url}  {detail}".rstrip())
            if state == "gone":
                gone.append((path, url, status))
    if gone:
        print("\nLinks that are gone (404/410):")
        for path, url, status in gone:
            print(f"  {path}: {url} -> {status}")
        return 1
    print("\nno link is gone")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["docs/checklist.html", "docs/check-company.html"]))
