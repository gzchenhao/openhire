"""The 三不原则 in README are claims about code; this pins each one to the code.

1. No résumé, ever: tests/test_privacy.py already pins the protocol and the refusal of
   résumé-shaped arguments. Here: the words the README uses must stay in the README.
2. Never applies for you: nothing in the apply path or the client can make an HTTP request.
3. No tracking: no analytics, telemetry or view counting anywhere in the package.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_readme_states_the_three_nos():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in ("不存简历", "不刷假单", "不追踪", "No résumé, ever", "Never applies for you", "No tracking"):
        assert phrase in readme, phrase


def test_apply_path_cannot_make_network_requests():
    from openhire import client, service

    for mod in (service, client):
        src = inspect.getsource(mod)
        for token in ("httpx", "requests.", "urllib.request", "aiohttp", "socket."):
            assert token not in src, f"{mod.__name__} mentions {token}: the apply path must never call out"


def test_no_tracking_code_anywhere():
    pkg = ROOT / "src" / "openhire"
    forbidden = re.compile(r"\b(telemetry|analytics|posthog|mixpanel|segment\.io|google-analytics|sentry_sdk)\b", re.I)
    hits = []
    for path in pkg.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in forbidden.finditer(text):
            # the extractor's role-family vocabulary legitimately lists "analytics" as a job word
            line = text[: m.start()].count("\n") + 1
            if path.name == "extract.py" and m.group(0).lower() == "analytics":
                continue
            hits.append(f"{path.relative_to(ROOT)}:{line}:{m.group(0)}")
    assert not hits, hits
