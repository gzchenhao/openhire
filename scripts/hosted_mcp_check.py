"""Ask a hosted OpenHire endpoint what every MCP client asks first: initialize, then tools/list.

Usage: python3 scripts/hosted_mcp_check.py <base-url> [expected-version]

Exit 0 when both answer 200 with the server's own name (and the expected version, if
given) and the tool list carries search_jobs; 1 otherwise. deploy-hosted.yml runs it after
each deploy and in the daily check, because /healthz can be green while /mcp refuses every
client: 0.8.15 on Render answered 421 Misdirected Request to all of them (2026-10-20).
Standard library only, so it runs on a bare runner.
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
    return problems


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
