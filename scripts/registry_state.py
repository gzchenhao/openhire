"""What the official MCP Registry serves for this server: a helper for the publish workflow.

    python3 scripts/registry_state.py 0.8.8

prints one line (`http=200 versions=[...] latest=0.8.7 present=True`) and exits
    0  the wanted version is flagged `isLatest`
    2  the wanted version is in the registry but not (yet) flagged latest
    1  the registry answered and does not have that version
    3  the registry could not be read (network, non-200, not JSON)

Why: the workflow's check used to be an inline one-liner that printed `none` both when the
request failed and when the index was mid-update. On 2026-10-14 the 0.8.8 publish succeeded
and the search index then served no `isLatest` entry at all for over a minute, so the
check called a good release a failure (the third such false alarm after 0.8.2 and 0.8.3).
The workflow now polls on 2 and 3 and fails only on 1: a version that is in the registry
was published; which entry carries the flag is the index's business.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request

SERVER = "io.github.gzchenhao/openhire"
URL = f"https://registry.modelcontextprotocol.io/v0/servers?search={SERVER}"
FLAG = "io.modelcontextprotocol.registry/official"


USER_AGENT = "openhire-release-check/1 (+https://github.com/gzchenhao/openhire)"


def read(url: str = URL) -> tuple[int, str]:
    """HTTP status and body; status 0 when the request itself failed.

    curl first, the way the inline check always read the registry within a second; urllib
    only if curl is missing. The first version of this script used urllib alone and sat on
    its 30 s timeout on the runner (2026-10-14, run 38514031731) while curl kept answering."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        r = subprocess.run(
            ["curl", "-sS", "--max-time", "20", "-A", USER_AGENT, "-H", "Accept: application/json",
             "-o", "-", "-w", "\n%{http_code}", url],
            capture_output=True, text=True, timeout=30, check=False,
        )
        body, _, status = r.stdout.rpartition("\n")
        if r.returncode == 0 and status.isdigit():
            return int(status), body
        note = r.stderr.strip() or f"curl exit {r.returncode}"
    except (OSError, subprocess.SubprocessError) as e:
        note = f"{type(e).__name__}: {e}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # DNS, timeout, TLS: the registry was not reached
        return 0, f"curl: {note}; urllib: {type(e).__name__}: {e}"


def parse(text: str) -> tuple[list[str], str | None]:
    """Every version the search lists for THIS server (the search is a substring match, so
    other servers can appear), and the one flagged latest if any."""
    data = json.loads(text)
    mine = [s for s in data.get("servers", []) if isinstance(s, dict) and (s.get("server") or {}).get("name") == SERVER]
    versions = [str((s.get("server") or {}).get("version")) for s in mine]
    latest = [str(s["server"].get("version")) for s in mine if ((s.get("_meta") or {}).get(FLAG) or {}).get("isLatest")]
    return versions, (latest[0] if latest else None)


def state(want: str, status: int, text: str) -> tuple[int, str]:
    """The exit code and the line to print."""
    if status != 200:
        return 3, f"http={status} unreadable: {text[:120]!r}"
    try:
        versions, latest = parse(text)
    except (ValueError, AttributeError, TypeError) as e:
        return 3, f"http={status} not the registry's JSON: {type(e).__name__}"
    line = f"http={status} versions={versions} latest={latest} present={want in versions}"
    if latest == want:
        return 0, line
    if want in versions:
        return 2, line
    return 1, line


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: registry_state.py <version>", file=sys.stderr)
        return 64
    status, text = read()
    code, line = state(argv[1], status, text)
    print(f"want={argv[1]} {line} exit={code}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
