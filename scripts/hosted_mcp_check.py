"""Ask a hosted OpenHire endpoint what every MCP client asks first: initialize, then tools/list,
then one watch_intent / check_watches round trip.

Usage: python3 scripts/hosted_mcp_check.py <base-url> [expected-version]

Exit 0 when initialize and tools/list answer 200 with the server's own name (and the
expected version, if given), the tool list carries search_jobs, and a throwaway watch can be
registered and pulled back; 1 otherwise. deploy-hosted.yml runs it after each deploy and in
the daily check, because /healthz can be green while /mcp refuses every client: 0.8.15 on
Render answered 421 Misdirected Request to all of them (2026-10-20), and until 0.8.29 every
watch_intent on the host failed because the bootstrapped index had no watches table
(reports/098). Standard library only, so it runs on a bare runner.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

PROTOCOL = "2025-06-18"


def _post(url: str, payload: dict, protocol: str | None = None) -> tuple[int, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "User-Agent": "openhire-deploy-check"}
    if protocol:
        headers["MCP-Protocol-Version"] = protocol
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _message(body: str) -> dict:
    """The JSON-RPC message in a plain JSON body or in the data lines of an SSE body."""
    text = body.strip()
    if text.startswith("{"):
        return json.loads(text)
    data = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
    return json.loads("".join(data)) if data else {}


def check(base: str, expected_version: str | None = None) -> list[str]:
    """Problems found; empty when the endpoint answers like an MCP server should."""
    url = base.rstrip("/") + "/mcp"
    status, body = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": PROTOCOL, "capabilities": {},
        "clientInfo": {"name": "openhire-deploy-check", "version": "1"}}})
    if status != 200:
        return [f"initialize: HTTP {status} {body[:200]!r}"]
    info = (_message(body).get("result") or {}).get("serverInfo") or {}
    problems = []
    if info.get("name") != "openhire":
        problems.append(f"initialize: unexpected serverInfo {info!r}")
    if expected_version and info.get("version") != expected_version:
        problems.append(f"initialize: version {info.get('version')!r}, expected {expected_version!r}")
    status, body = _post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, PROTOCOL)
    if status != 200:
        return problems + [f"tools/list: HTTP {status} {body[:200]!r}"]
    tools = [t.get("name") for t in (_message(body).get("result") or {}).get("tools") or []]
    if "search_jobs" not in tools:
        problems.append(f"tools/list: search_jobs missing from {tools!r}")
    else:
        print(f"{url}: openhire {info.get('version')} answers initialize and tools/list ({len(tools)} tools)")
    problems += _watch_round_trip(url)
    return problems


def _call(url: str, id_: int, name: str, arguments: dict) -> tuple[int, dict | None]:
    """tools/call, with the tool's own result dict (structuredContent, or the JSON text)."""
    status, body = _post(url, {"jsonrpc": "2.0", "id": id_, "method": "tools/call",
                               "params": {"name": name, "arguments": arguments}}, PROTOCOL)
    if status != 200:
        return status, None
    result = _message(body).get("result") or {}
    payload = result.get("structuredContent")
    if payload is None:
        texts = [c.get("text") for c in result.get("content") or [] if c.get("type") == "text"]
        try:
            payload = json.loads(texts[0]) if texts else None
        except (json.JSONDecodeError, TypeError):
            payload = None
    return status, payload if isinstance(payload, dict) else None


def _find(payload: dict | None, key: str):
    """The first value under `key` at any depth: FastMCP may wrap a dict result once."""
    if not isinstance(payload, dict):
        return None
    if key in payload:
        return payload[key]
    for v in payload.values():
        if isinstance(v, dict):
            found = _find(v, key)
            if found is not None:
                return found
    return None


def _watch_round_trip(url: str) -> list[str]:
    """Register a throwaway watch and pull it back: proves the user-state tables exist.

    A hosted instance bootstraps from the public snapshot on every cold start, and that
    snapshot carries no `watches` table; until 0.8.29 nothing created it after the download,
    so every watch_intent on the host failed with "no such table: watches" while /healthz
    and tools/list stayed green (reports/098). The filter matches no posting on purpose, so
    the check costs one small row, under a fingerprint nobody else uses."""
    import secrets

    fp = f"#deploy-check-{secrets.token_hex(4)}"
    status, reg = _call(url, 3, "watch_intent", {"fingerprint": fp, "filters": {"title": ["openhire-deploy-check-no-such-title"]}})
    if status != 200:
        return [f"watch_intent: HTTP {status}"]
    watch_id = _find(reg, "watch_id")
    if not (isinstance(watch_id, str) and watch_id.startswith("w_")):
        return [f"watch_intent: no watch_id in {str(reg)[:300]!r} (is the watches table missing after bootstrap?)"]
    status, pulled = _call(url, 4, "check_watches", {"fingerprint": fp})
    if status != 200:
        return [f"check_watches: HTTP {status}"]
    ids = [r.get("watch_id") for r in (_find(pulled, "results") or []) if isinstance(r, dict)]
    if watch_id not in ids:
        return [f"check_watches: {watch_id} not returned in {str(pulled)[:300]!r}"]
    print(f"{url}: watch_intent and check_watches round trip ok ({watch_id})")
    return []


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[2])
        return 2
    problems = check(argv[1], argv[2] if len(argv) > 2 else None)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
