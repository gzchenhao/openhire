"""Hosted mode: the same server, run by the maintainer at a public URL.

Why: ChatGPT (and any client that only takes a URL) cannot start a local process, so for
those users OpenHire has to be reachable somewhere. Everything that reaches this host is
what the tools take by protocol: search filters, a company name or domain, a board URL, an
anonymous client-generated fingerprint. A résumé, name, email or phone never fits through
any tool (tests/test_privacy.py). The local install stays the recommended path: there,
nothing of a search leaves the user's machine, and watches live on their own disk.

What hosted mode adds to `ohp serve --transport streamable-http`:
  - a landing page at `/`, a `/livez` for the platform's health check and a `/healthz`
    for monitors (version, index state);
  - a sentence in the MCP `instructions` saying where a request goes;
  - a per-IP and a global rate limit (a public URL with no auth needs one);
  - stateless streamable HTTP (a restart does not strand sessions);
  - a worker that notices the new weekly snapshot, stages it next to the live index and
    restarts the process to activate it, carrying watches and application records over
    (`pipeline/snapshot.py`; the restart loop is hosted/entrypoint.sh).

Turned on with OPENHIRE_HOSTED=1. Nothing here runs in local mode.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import __version__

ENV_FLAG = "OPENHIRE_HOSTED"
REPO_URL = "https://github.com/gzchenhao/openhire"
PRIVACY_URL = f"{REPO_URL}/blob/main/docs/PRIVACY.md"
DEFAULT_PUBLIC_URL = "https://openhire-vlny.onrender.com"
MCP_PATH = "/mcp"

# Appended to the server's MCP instructions in hosted mode, so the agent can tell the user
# where this request goes and what the alternative is.
NOTICE = (
    " HOSTED ENDPOINT: this server is run by the maintainer (gzchenhao) at a public URL for "
    "clients that can only reach a URL, such as ChatGPT connectors. What reaches this host is "
    "exactly what the tools take: search filters, a company name or domain, a board URL, the "
    "anonymous fingerprint. No résumé, name, email or phone, ever. The host keeps no log of "
    "queries. Watches and application records are stored in this host's index, keyed by the "
    "fingerprint, and carried over across index refreshes; for a watch that lives on the user's "
    "own disk, run OpenHire locally (`uvx openhire serve`). Privacy terms: " + PRIVACY_URL
)


def is_hosted() -> bool:
    return os.environ.get(ENV_FLAG, "").strip().lower() not in ("", "0", "false", "no")


def public_url() -> str:
    explicit = os.environ.get("OPENHIRE_HOSTED_PUBLIC_URL")
    if explicit:
        return explicit.rstrip("/")
    render = os.environ.get("RENDER_EXTERNAL_URL")  # set by Render
    if render:
        return render.rstrip("/")
    space_host = os.environ.get("SPACE_HOST")  # set by Hugging Face Spaces
    if space_host:
        return f"https://{space_host}".rstrip("/")
    return DEFAULT_PUBLIC_URL


# --- rate limit ----------------------------------------------------------------------------
class RateLimit:
    """Fixed one-minute windows, per client address and for the host as a whole.

    Pure ASGI so it wraps the SDK's Starlette app without touching it; lifespan and other
    non-HTTP scopes pass straight through. Exempt paths are what monitors poll. The per-IP
    figure is generous on purpose: ChatGPT's connector traffic for many users arrives from a
    few egress addresses, and the limit is there against a runaway client, not against use.
    """

    def __init__(self, app, per_ip: int = 300, total: int = 3000, window: float = 60.0,
                 exempt: tuple[str, ...] = ("/", "/healthz", "/livez"), clock: Callable[[], float] = time.monotonic):
        self.app = app
        self.per_ip = per_ip
        self.total = total
        self.window = window
        self.exempt = set(exempt)
        self.clock = clock
        self.lock = threading.Lock()
        self.window_start = clock()
        self.counts: dict[str, int] = {}
        self.total_count = 0

    @staticmethod
    def client_ip(scope: dict) -> str:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        forwarded = headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip() or "?"
        client = scope.get("client")
        return client[0] if client else "?"

    def allow(self, ip: str) -> tuple[bool, int]:
        """(allowed, seconds until the window resets)."""
        now = self.clock()
        with self.lock:
            if now - self.window_start >= self.window:
                self.window_start = now
                self.counts = {}
                self.total_count = 0
            self.total_count += 1
            n = self.counts.get(ip, 0) + 1
            self.counts[ip] = n
            retry = int(self.window - (now - self.window_start)) + 1
            if n > self.per_ip or self.total_count > self.total:
                return False, retry
            return True, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in self.exempt:
            await self.app(scope, receive, send)
            return
        ok, retry = self.allow(self.client_ip(scope))
        if ok:
            await self.app(scope, receive, send)
            return
        body = json.dumps({
            "error": "rate_limited",
            "message": (f"too many requests from this address; try again in {retry} s, "
                        "or run OpenHire locally (uvx openhire serve)"),
        }).encode("utf-8")
        await send({"type": "http.response.start", "status": 429, "headers": [
            (b"content-type", b"application/json"),
            (b"retry-after", str(retry).encode("ascii")),
            (b"content-length", str(len(body)).encode("ascii")),
        ]})
        await send({"type": "http.response.body", "body": body})


# --- index state ---------------------------------------------------------------------------
def index_stats() -> dict[str, Any]:
    """Counts a monitor and the landing page show. The public numbers people may quote are
    still docs/numbers.json; this is only 'is the index loaded and how old is it'."""
    from sqlalchemy import func, select

    from .db import session_scope
    from .db.models import Company, Job

    try:
        with session_scope() as s:
            companies = s.scalar(select(func.count()).select_from(Company)) or 0
            jobs = s.scalar(select(func.count()).select_from(Job)) or 0
            as_of = s.scalar(select(func.max(Job.verified_at)))
    except Exception as e:  # a half-installed index must not take the health route down
        return {"companies": 0, "jobs": 0, "data_as_of": None, "error": f"{type(e).__name__}: {e}"}
    if isinstance(as_of, dt.datetime):
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=dt.timezone.utc)
        as_of_s: str | None = as_of.isoformat()
        age: int | None = (dt.datetime.now(dt.timezone.utc) - as_of).days
    else:
        as_of_s, age = (str(as_of) if as_of else None), None
    return {"companies": companies, "jobs": jobs, "data_as_of": as_of_s, "data_age_days": age}


def health() -> tuple[int, dict[str, Any]]:
    stats = index_stats()
    ready = stats["jobs"] > 0
    body = {"status": "ok" if ready else "index_empty", "version": __version__,
            "index_ready": ready, **stats, "mcp": f"{public_url()}{MCP_PATH}"}
    return (200 if ready else 503), body


def page_html(name: str) -> str:
    """A static page shipped in the package (src/openhire/pages), the same bytes as docs/."""
    from importlib import resources

    return resources.files("openhire.pages").joinpath(name).read_text(encoding="utf-8")


def checklist_html() -> str:
    return page_html("checklist.html")


def landing_html() -> str:
    stats = index_stats()
    url = public_url()
    as_of = (stats.get("data_as_of") or "")[:10] or "not loaded yet"
    e = html.escape
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>OpenHire hosted endpoint</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
code{{background:#f3f3f3;padding:.1em .3em;border-radius:3px}} h1{{font-size:1.5rem}} li{{margin:.25rem 0}}</style></head>
<body>
<h1>OpenHire · hosted MCP endpoint</h1>
<p><b>Companies screen you with AI. Screen them back. 已读不回？先看岗位还在不在。</b></p>
<p>Let an AI assistant find jobs for you straight from employers' own systems, with your résumé never leaving your computer.
Is the job still open? Is the company real? Check both before you apply.<br>
让 AI 助手直接从雇主自己的系统里替你找工作，简历不出你的电脑。岗位还在不在，公司真不真，投之前先查一遍。</p>
<p>MCP endpoint: <code>{e(url)}{MCP_PATH}</code> (streamable HTTP, no authentication) · version {e(__version__)} ·
index: {stats.get('companies', 0)} employers, {stats.get('jobs', 0):,} postings, data as of {e(as_of)}.</p>
<h2>Connect</h2>
<p><b>Not sure which steps are yours?</b> The <a href="{e(url)}/connect">connect guide · 连接向导</a> asks which assistant you use and shows only that one's steps, with the one block to paste. 选你用的助手，只看那一种的步骤。</p>
<ul>
<li><b>ChatGPT</b> (paid plans): Settings → Connectors → Advanced → turn on Developer mode → Create → name <code>OpenHire</code>,
URL <code>{e(url)}{MCP_PATH}</code>, authentication none. Then ask, in a new chat with the connector enabled, for example:
<i>which embodied-AI companies are hiring perception engineers, with the employer's own posting date and days open?</i></li>
<li><b>Any MCP client that takes a URL</b> (豆包 custom connector, Cherry Studio, Cline, Cursor…): add <code>{e(url)}{MCP_PATH}</code> as a streamable-HTTP server.</li>
<li><b>Prefer it on your own machine</b> (recommended): <code>uvx openhire serve</code>, one line of config in Claude, 豆包, DeepSeek (via Cherry Studio / Chatbox), Cursor or 腾讯 WorkBuddy. Then nothing of a search leaves your computer.</li>
</ul>
<h2>Pages · 页面</h2>
<ul>
<li><a href="{e(url)}/connect">连接向导</a>：选你用的 AI 助手（ChatGPT、Claude、豆包、DeepSeek、Cursor、腾讯 WorkBuddy、VS Code），只看那一种的接入步骤和一段整段粘贴的话。</li>
<li><a href="{e(url)}/checklist">求职清单</a>：找工作每一步该做什么、哪步能让 AI 替你做、查公司和防骗去哪个官网，一页写全，免费，不用注册，中英文可切换。</li>
<li><a href="{e(url)}/check-company">查公司</a>：入职前核一家公司去哪些官方网站，怎么识别冒充用人方的骗局。</li>
<li><a href="{e(url)}/portals">读不到的招聘门户</a>：岗位放在飞书、BOSS 直聘或没有可读列表的官网上的公司，它们自己的招聘页链接。</li>
<li><a href="https://gzchenhao.github.io/openhire/employers.html">给雇主</a> · <a href="{e(PRIVACY_URL)}">隐私说明</a> · <a href="{e(REPO_URL)}">源码</a>（GitHub 不通时：<a href="https://cnb.cool/gzchenhao/openhire">cnb.cool 镜像</a>）</li>
</ul>
<h2>What this host sees</h2>
<ul>
<li>Exactly what the tools take: search filters, a company name or domain, a board URL, an anonymous client-generated fingerprint. No résumé, name, email or phone, ever, by protocol.</li>
<li>No query log. Watches and application records are kept in this host's index, keyed by the fingerprint, and carried over when the index is refreshed; they do not survive a rebuild of the host. For a durable watch, run OpenHire locally.</li>
<li>Rate limit per address; the index is the public weekly snapshot, refreshed in place.</li>
<li>Full terms: <a href="{e(PRIVACY_URL)}">privacy policy</a> · source and numbers: <a href="{e(REPO_URL)}">{e(REPO_URL)}</a></li>
</ul>
<hr>
<p>数据有误或想更正贵公司的岗位状态？<a href="https://github.com/gzchenhao/openhire/issues/new?template=employer_claim.yml">雇主认领入口</a>，免费，也可以直接要求我们把贵公司从索引中移除。</p>
</body></html>
"""


# --- snapshot refresh worker ----------------------------------------------------------------
def marker_path(db_path: str | Path) -> Path:
    p = Path(db_path)
    return p.with_name(p.name + ".snapshot-fingerprint")


def check_once(snapshot_url: str, db_path: str | Path, marker: Path | None = None,
               log: Callable[[str], None] = lambda m: print(m, file=sys.stderr)) -> bool:
    """One refresh check. True when a new snapshot was staged (the caller then restarts)."""
    from .pipeline import snapshot as _snapshot

    marker = marker or marker_path(db_path)
    fp = _snapshot.snapshot_fingerprint(snapshot_url)
    if not fp:
        return False
    seen = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    if not seen:
        # First look after a start: the index was just bootstrapped from this very asset.
        marker.write_text(fp, encoding="utf-8")
        return False
    if fp == seen:
        return False
    try:
        res = _snapshot.stage_snapshot(snapshot_url, db_path)
    except Exception as e:  # keep serving the old index; try again next round
        log(f"openhire: staging the new snapshot failed ({type(e).__name__}: {e}); will retry")
        return False
    marker.write_text(fp, encoding="utf-8")
    log(f"openhire: new snapshot staged ({res.companies} employers, {res.jobs:,} jobs, "
        f"data as of {res.data_as_of}); restarting to activate it")
    return True


def start_refresh_worker(snapshot_url: str, db_path: str | Path, wait_index: Callable[[], None],
                         hours: float) -> threading.Thread:
    """Every `hours`, ask the snapshot source whether it changed; if so stage it and stop the
    process (SIGTERM to self: uvicorn shuts down cleanly, the restart loop starts us again,
    and `serve()` activates the staged file before anything opens the index)."""

    def loop() -> None:
        wait_index()
        try:
            check_once(snapshot_url, db_path)  # records the fingerprint of what we booted from
        except Exception as e:
            print(f"openhire: refresh worker: {type(e).__name__}: {e}", file=sys.stderr)
        while True:
            time.sleep(max(hours, 0.05) * 3600)
            try:
                if check_once(snapshot_url, db_path):
                    os.kill(os.getpid(), signal.SIGTERM)
                    return
            except Exception as e:
                print(f"openhire: refresh worker: {type(e).__name__}: {e}", file=sys.stderr)

    t = threading.Thread(target=loop, name="openhire-hosted-refresh", daemon=True)
    t.start()
    return t


# --- app assembly --------------------------------------------------------------------------
_ROUTES_REGISTERED = False
_APP = None


def build_app(mcp, per_ip: int | None = None, total: int | None = None):
    """The ASGI app for hosted mode: the SDK's streamable-HTTP app plus `/`, `/healthz` and
    the rate limit. Built once per process (the SDK's session manager runs once)."""
    global _ROUTES_REGISTERED, _APP
    if _APP is not None:
        return _APP
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, JSONResponse

    if not _ROUTES_REGISTERED:
        @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
        async def _healthz(_: Request):
            code, body = health()
            return JSONResponse(body, status_code=code)

        @mcp.custom_route("/livez", methods=["GET"], include_in_schema=False)
        async def _livez(_: Request):
            # 200 as soon as the process answers, before the snapshot is loaded: what a
            # platform's own health check (Render, a load balancer) should poll. /healthz
            # is the stricter "ready with data" answer for monitors.
            return JSONResponse({"status": "alive", "version": __version__})

        @mcp.custom_route("/", methods=["GET"], include_in_schema=False)
        async def _landing(_: Request):
            return HTMLResponse(landing_html())

        # The job-search checklist, served here too because github.io is often unreachable
        # from mainland China (the maintainer, 2026-10-21). Same file as docs/checklist.html.
        @mcp.custom_route("/checklist", methods=["GET"], include_in_schema=False)
        @mcp.custom_route("/checklist.html", methods=["GET"], include_in_schema=False)
        async def _checklist(_: Request):
            return HTMLResponse(checklist_html())

        # 查公司: the official places to verify a company and the anti-scam steps, and nothing
        # else. A third-party site (EarlyTip, a personal-ICP-filed news site) links here, on
        # the condition that this page never carries job listings, an install guide, the
        # product's name or any 求职 / 招聘 / 岗位 wording (reports/088); tests/test_hosted.py
        # pins that. `?from=<site>` is accepted and ignored: this host keeps no log.
        @mcp.custom_route("/check-company", methods=["GET"], include_in_schema=False)
        @mcp.custom_route("/check-company.html", methods=["GET"], include_in_schema=False)
        async def _check_company(_: Request):
            return HTMLResponse(page_html("check-company.html"))

        # The connect guide (0.8.30, reports/100): pick your assistant, get only its steps and
        # the one block to paste. The answer to "the first connection is the hard part", with no
        # postings on it. Same file as docs/connect.html.
        @mcp.custom_route("/connect", methods=["GET"], include_in_schema=False)
        @mcp.custom_route("/connect.html", methods=["GET"], include_in_schema=False)
        async def _connect(_: Request):
            return HTMLResponse(page_html("connect.html"))

        # The same page as a feed EarlyTip renders as its own 查公司 column (reports/095),
        # built from the packaged page, byte for byte docs/check-company.json.
        @mcp.custom_route("/check-company.json", methods=["GET"], include_in_schema=False)
        async def _check_company_feed(_: Request):
            from starlette.responses import Response

            from .check_company_feed import build, dumps

            return Response(dumps(build(page_html("check-company.html"))),
                            media_type="application/json; charset=utf-8",
                            headers={"Access-Control-Allow-Origin": "*"})

        # The portal directory, rendered from the registry (the same page as docs/portals.html).
        @mcp.custom_route("/portals", methods=["GET"], include_in_schema=False)
        @mcp.custom_route("/portals.html", methods=["GET"], include_in_schema=False)
        async def _portals(_: Request):
            from .portals_page import render

            return HTMLResponse(render())

        _ROUTES_REGISTERED = True

    if not (mcp._mcp_server.instructions or "").endswith(NOTICE):
        mcp._mcp_server.instructions = (mcp._mcp_server.instructions or "") + NOTICE
    mcp.settings.stateless_http = True
    inner = mcp.streamable_http_app()
    _APP = RateLimit(
        inner,
        per_ip=per_ip or int(os.environ.get("OPENHIRE_HOSTED_RATE_PER_IP", "300")),
        total=total or int(os.environ.get("OPENHIRE_HOSTED_RATE_TOTAL", "3000")),
    )
    return _APP


def serve(mcp, host: str, port: int, snapshot_url: str, db_path: str,
          wait_index: Callable[[], None]) -> None:
    """Run hosted mode: build the app, start the refresh worker, serve with uvicorn."""
    import logging

    import uvicorn

    # Stateless HTTP makes the SDK log "Terminating session" on every request; keep its
    # INFO chatter out of the host's logs (warnings and errors still show).
    logging.getLogger("mcp").setLevel(logging.WARNING)
    app = build_app(mcp)
    hours = float(os.environ.get("OPENHIRE_HOSTED_REFRESH_HOURS", "6"))
    start_refresh_worker(snapshot_url, db_path, wait_index, hours)
    print(f"openhire {__version__}: hosted mode on {host}:{port}{MCP_PATH} (public {public_url()}{MCP_PATH}); "
          f"snapshot checked every {hours:g} h", file=sys.stderr)
    # access_log off: request lines carry client addresses, and the host keeps no log of use.
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False,
                proxy_headers=True, forwarded_allow_ips="*")
