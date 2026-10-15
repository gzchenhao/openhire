"""Hosted mode (0.8.11): the same server at a public URL for clients that only take a URL.

What these pin: the flag, the two monitor routes, the privacy sentence in the MCP
instructions and on the landing page, the rate limit, and the refresh worker's decision
(stage and restart only when the published snapshot actually changed)."""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from openhire import hosted


def test_flag_reads_the_environment(monkeypatch):
    monkeypatch.delenv(hosted.ENV_FLAG, raising=False)
    assert hosted.is_hosted() is False
    monkeypatch.setenv(hosted.ENV_FLAG, "0")
    assert hosted.is_hosted() is False
    monkeypatch.setenv(hosted.ENV_FLAG, "1")
    assert hosted.is_hosted() is True


def test_public_url_prefers_explicit_then_space_host(monkeypatch):
    monkeypatch.delenv("OPENHIRE_HOSTED_PUBLIC_URL", raising=False)
    monkeypatch.delenv("SPACE_HOST", raising=False)
    assert hosted.public_url() == hosted.DEFAULT_PUBLIC_URL
    monkeypatch.setenv("SPACE_HOST", "someone-openhire.hf.space")
    assert hosted.public_url() == "https://someone-openhire.hf.space"
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://openhire-abcd.onrender.com/")
    assert hosted.public_url() == "https://openhire-abcd.onrender.com"
    monkeypatch.setenv("OPENHIRE_HOSTED_PUBLIC_URL", "https://jobs.example.org/")
    assert hosted.public_url() == "https://jobs.example.org"


# --- routes --------------------------------------------------------------------------------
@pytest.fixture()
def client():
    """A test client on the hosted app. No lifespan: the two monitor routes need none, and
    the SDK's session manager may only be started once per process."""
    from starlette.testclient import TestClient

    from openhire.mcp_server import mcp

    app = hosted.build_app(mcp)
    return TestClient(app)


def _seed_one_job():
    from openhire.db import init_db, session_scope
    from openhire.db.models import Company, Job

    init_db()
    now = dt.datetime.now(dt.timezone.utc)
    with session_scope() as s:
        if s.get(Company, "hosted-acme") is None:
            s.add(Company(id="hosted-acme", name="Hosted Acme", ats_vendor="greenhouse",
                          ats_tenant="hosted-acme", careers_url="x", last_crawled_at=now))
            s.add(Job(id="hosted-acme:1", company_id="hosted-acme", title="Perception Engineer",
                      description_raw="x", skills=["c++"], remote_policy="remote", first_seen_at=now,
                      verified_at=now, source="ats_public_api", ghost_score=0.0,
                      role_family="engineering",
                      apply_channel="https://boards.greenhouse.io/embed/job_app?for=hosted-acme&token=1",
                      content_hash="hosted-h1"))


def test_healthz_says_empty_then_ready(client):
    from openhire.db import init_db, session_scope
    from openhire.db.models import Job

    init_db()
    with session_scope() as s:
        empty = s.query(Job).count() == 0
    r = client.get("/healthz")
    assert r.status_code in (200, 503)
    body = r.json()
    assert body["version"] and body["mcp"].endswith("/mcp")
    if empty:
        assert r.status_code == 503 and body["index_ready"] is False
    _seed_one_job()
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["index_ready"] is True and body["jobs"] >= 1 and body["data_as_of"]


def test_livez_answers_before_the_index_is_loaded(client):
    r = client.get("/livez")
    assert r.status_code == 200 and r.json()["status"] == "alive" and r.json()["version"]


def test_landing_page_states_the_posture_and_the_endpoint(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    page = r.text
    assert "/mcp" in page
    assert hosted.PRIVACY_URL in page and hosted.REPO_URL in page
    assert "简历不出你的电脑" in page
    assert "No résumé, name, email or phone" in page
    assert "ChatGPT" in page and "uvx openhire serve" in page


def test_instructions_carry_the_hosted_notice_once(client):
    from openhire.mcp_server import mcp

    text = mcp.instructions or ""
    assert text.endswith(hosted.NOTICE)
    assert text.count("HOSTED ENDPOINT") == 1
    hosted.build_app(mcp)  # a second build must not append again
    assert (mcp.instructions or "").count("HOSTED ENDPOINT") == 1


# --- rate limit ----------------------------------------------------------------------------
def _run(app, path="/mcp", ip="203.0.113.9", forwarded=None):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    scope = {"type": "http", "path": path, "headers": headers, "client": (ip, 1234), "method": "POST"}
    asyncio.run(app(scope, receive, send))
    return sent


def _ok_app():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    return app


def test_rate_limit_per_address_then_429_with_retry_after():
    limited = hosted.RateLimit(_ok_app(), per_ip=3, total=100, exempt=())
    for _ in range(3):
        assert _run(limited)[0]["status"] == 200
    sent = _run(limited)
    assert sent[0]["status"] == 429
    assert any(k == b"retry-after" for k, _ in sent[0]["headers"])
    assert b"rate_limited" in sent[1]["body"]
    # Another address is unaffected; the proxy's X-Forwarded-For is what counts.
    assert _run(limited, ip="198.51.100.1")[0]["status"] == 200
    assert _run(limited, forwarded="198.51.100.2, 10.0.0.1")[0]["status"] == 200


def test_rate_limit_window_resets_and_exempts_monitor_paths():
    clock = {"t": 1000.0}
    limited = hosted.RateLimit(_ok_app(), per_ip=1, total=100, window=60.0, exempt=("/healthz",),
                               clock=lambda: clock["t"])
    assert _run(limited)[0]["status"] == 200
    assert _run(limited)[0]["status"] == 429
    assert _run(limited, path="/healthz")[0]["status"] == 200  # exempt
    clock["t"] += 61
    assert _run(limited)[0]["status"] == 200


def test_global_cap_applies_across_addresses():
    limited = hosted.RateLimit(_ok_app(), per_ip=100, total=2, exempt=())
    assert _run(limited, ip="1.1.1.1")[0]["status"] == 200
    assert _run(limited, ip="2.2.2.2")[0]["status"] == 200
    assert _run(limited, ip="3.3.3.3")[0]["status"] == 429


def test_lifespan_and_non_http_scopes_pass_through():
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    limited = hosted.RateLimit(app, per_ip=0, total=0, exempt=())
    asyncio.run(limited({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


# --- refresh worker ------------------------------------------------------------------------
def test_check_once_stages_only_when_the_snapshot_changed(tmp_path, monkeypatch):
    from openhire.pipeline import snapshot as snap

    staged = []
    fps = {"v": "etag-1|100|Mon"}
    monkeypatch.setattr(snap, "snapshot_fingerprint", lambda url: fps["v"])

    class Res:
        companies, jobs, data_as_of = 1, 1, "2026-10-13"

    monkeypatch.setattr(snap, "stage_snapshot", lambda url, db: staged.append(url) or Res())
    marker = tmp_path / "m"
    logs: list[str] = []

    # First look records what we booted from and does not restart.
    assert hosted.check_once("https://x/snap.gz", tmp_path / "db", marker, logs.append) is False
    assert marker.read_text() == "etag-1|100|Mon" and staged == []
    # Unchanged: nothing.
    assert hosted.check_once("https://x/snap.gz", tmp_path / "db", marker, logs.append) is False
    assert staged == []
    # Changed: staged, marker advanced, restart requested.
    fps["v"] = "etag-2|120|Tue"
    assert hosted.check_once("https://x/snap.gz", tmp_path / "db", marker, logs.append) is True
    assert staged == ["https://x/snap.gz"] and marker.read_text() == "etag-2|120|Tue"
    assert any("restarting" in m for m in logs)
    # Source unreachable (no fingerprint): nothing, and the marker is untouched.
    fps["v"] = None
    assert hosted.check_once("https://x/snap.gz", tmp_path / "db", marker, logs.append) is False
    assert marker.read_text() == "etag-2|120|Tue"


def test_check_once_keeps_the_old_index_when_staging_fails(tmp_path, monkeypatch):
    from openhire.pipeline import snapshot as snap

    monkeypatch.setattr(snap, "snapshot_fingerprint", lambda url: "etag-9")
    marker = tmp_path / "m"
    marker.write_text("etag-1")

    def boom(url, db):
        raise snap.SnapshotError("0 jobs")

    monkeypatch.setattr(snap, "stage_snapshot", boom)
    logs: list[str] = []
    assert hosted.check_once("https://x/snap.gz", tmp_path / "db", marker, logs.append) is False
    assert marker.read_text() == "etag-1"  # will be retried next round
    assert any("failed" in m for m in logs)
