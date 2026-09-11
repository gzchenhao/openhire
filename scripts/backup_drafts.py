"""Sync drafts/ to the private backup repo (gzchenhao/openhire-private).

drafts/ is gitignored in the public repo on purpose — it holds promo copy, outreach
scripts and goal briefs we don't publish. It is also the only working content that is
NOT already backed up by pushing to GitHub, so it gets its own private mirror.

    .venv/Scripts/python.exe scripts/backup_drafts.py

Never syncs secrets: .env and friends are refused outright, not merely gitignored.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "https://github.com/gzchenhao/openhire-private.git"
SRC = Path(__file__).resolve().parent.parent / "drafts"
# Anything matching these never leaves this machine, private repo or not.
FORBIDDEN = ("*.env", ".env", "*.pem", "*.key", "*_token", "*.token", ".pypirc")


def run(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"$ {' '.join(args)}\n{r.stdout}{r.stderr}")
    return r.stdout.strip()


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"no drafts dir at {SRC}")
    leaked = [p.name for pat in FORBIDDEN for p in SRC.glob(pat)]
    if leaked:
        raise SystemExit(f"refusing to sync — secret-shaped files in drafts/: {leaked}")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        run("git", "clone", "--depth", "1", "-q", REPO, str(work))
        for item in work.iterdir():
            if item.name == ".git":
                continue
            shutil.rmtree(item) if item.is_dir() else item.unlink()
        readme = run("git", "show", "HEAD:README.md", cwd=work)
        for item in SRC.iterdir():
            if item.is_dir():
                shutil.copytree(item, work / item.name)
            else:
                shutil.copy2(item, work / item.name)
        (work / "README.md").write_text(readme + "\n", encoding="utf-8")

        run("git", "add", "-A", cwd=work)
        if not run("git", "status", "--porcelain", cwd=work):
            print("drafts already up to date — nothing to push")
            return
        run("git", "-c", "user.name=gzchenhao", "-c", "user.email=haolu98@icloud.com",
            "commit", "-q", "-m", "sync drafts", cwd=work)
        run("git", "push", "-q", "origin", "main", cwd=work)
        n = len(list(SRC.iterdir()))
        print(f"pushed {n} files to {REPO}")


if __name__ == "__main__":
    main()
