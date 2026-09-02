"""Weekly growth metrics from PUBLIC proxies only (local-first product = no telemetry).

The north-star metric (weekly active fingerprints) is unmeasurable by design — matching
runs on users' machines and nothing phones home. These public proxies stand in for it:
GitHub stars/traffic, PyPI downloads, and snapshot downloads (every `ohp bootstrap` pulls
the Release asset exactly once, so its download_count ≈ cumulative first-runs + CI runs).

Run:  .venv/Scripts/python.exe scripts/growth_metrics.py
Needs: gh (authenticated) on PATH; network to pypistats.org.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import urllib.request

REPO = "gzchenhao/openhire"


def gh(path: str) -> dict | list:
    out = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=True,
        encoding="utf-8",  # gh emits UTF-8; never trust the Windows codepage
    ).stdout
    return json.loads(out)


def pypi_downloads() -> dict:
    try:
        with urllib.request.urlopen(
            "https://pypistats.org/api/packages/openhire/recent", timeout=20
        ) as r:
            return json.load(r)["data"]
    except Exception as e:  # pypistats flakes sometimes; the row still prints
        return {"last_day": f"err:{e}", "last_week": "-", "last_month": "-"}


def main() -> None:
    repo = gh(f"repos/{REPO}")
    views = gh(f"repos/{REPO}/traffic/views")
    releases = gh(f"repos/{REPO}/releases")
    snap_dl = next(
        (
            a["download_count"]
            for rel in releases
            for a in rel.get("assets", [])
            if a["name"] == "openhire-index.db.gz"
        ),
        "n/a",
    )
    py = pypi_downloads()
    print(
        f"{dt.date.today()} | stars {repo['stargazers_count']} | forks {repo['forks_count']}"
        f" | views14d {views['count']} (uniq {views['uniques']})"
        f" | snapshot_dl {snap_dl}"
        f" | pypi d/w/m {py['last_day']}/{py['last_week']}/{py['last_month']}"
    )


if __name__ == "__main__":
    main()
