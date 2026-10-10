"""Sync drafts/ with the private repo (gzchenhao/openhire-private), both ways.

drafts/ is gitignored in the public repo on purpose: it holds promo copy, outreach
scripts and goal briefs we don't publish. Its home is the private repo, whose root is the
contents of drafts/.

    .venv/Scripts/python.exe scripts/backup_drafts.py
    .venv/Scripts/python.exe scripts/backup_drafts.py --resolved growth-log.md   # after a hand merge

Since 2026-10-10 the cloud sessions write drafts too (they commit straight to the private
repo; this machine only publishes them to Zhihu / 即刻 / X). The old one-way mirror would
have deleted every draft the cloud wrote, so the sync is now a three-way merge per file.
`drafts/.sync-state.json` remembers each file's content hash at the last sync, so the
script knows which side actually changed (timestamps lie: a copy or checkout moves them):
  * only the repo changed it, or only the repo has it: pulled into drafts/;
  * only this machine changed it, or only this machine has it: pushed;
  * both changed it differently: CONFLICT, nothing is overwritten. The repo's version is
    saved beside it in drafts/.sync-backup/<time>/ and the file is left for a human, who
    merges it into drafts/ and reruns with `--resolved <file>` to push the merged version.
  * no record yet and both differ (first run): the newer side wins, the loser is saved
    in drafts/.sync-backup/<time>/ first.
Line endings do not count as a change. Nothing is ever deleted on either side.

Never syncs secrets: .env and friends are refused outright in either direction.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = os.environ.get("OPENHIRE_DRAFTS_REPO", "https://github.com/gzchenhao/openhire-private.git")
SRC = Path(__file__).resolve().parent.parent / "drafts"
STATE = ".sync-state.json"
BACKUP_DIR = ".sync-backup"
SKIP_ROOT = {"README.md"}  # the private repo's own README, not a draft
# Anything matching these never moves, private repo or not.
FORBIDDEN = ("*.env", ".env", "*.pem", "*.key", "*_token", "*.token", ".pypirc")


def run(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"$ {' '.join(args)}\n{r.stdout}{r.stderr}")
    return r.stdout.strip()


def _files(root: Path) -> dict[str, Path]:
    out = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel.startswith((".git/", BACKUP_DIR + "/")) or rel in SKIP_ROOT or rel == STATE:
            continue
        out[rel] = p
    return out


def _hash(p: Path) -> str:
    """Content hash ignoring CRLF vs LF (Windows editors and git disagree; that is not an edit)."""
    crlf, lf = bytes([13, 10]), bytes([10])
    return hashlib.sha256(p.read_bytes().replace(crlf, lf)).hexdigest()


def _secret_shaped(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pat) for pat in FORBIDDEN)


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    resolved = set(argv[argv.index("--resolved") + 1:]) if "--resolved" in argv else set()
    if not SRC.is_dir():
        raise SystemExit(f"no drafts dir at {SRC}")
    local = _files(SRC)
    leaked = [r for r in local if _secret_shaped(r)]
    if leaked:
        raise SystemExit(f"refusing to sync: secret-shaped files in drafts/: {leaked}")
    state_path = SRC / STATE
    base: dict[str, str] = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        run("git", "-c", "core.autocrlf=false", "clone", "-q", REPO, str(work))
        remote = _files(work)
        leaked = [r for r in remote if _secret_shaped(r)]
        if leaked:
            raise SystemExit(f"refusing to sync: secret-shaped files in the private repo: {leaked}")

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        pulled, pushed, conflicts = [], [], []
        new_state: dict[str, str] = {}

        def save_aside(src: Path, rel: str, tag: str) -> None:
            dst = SRC / BACKUP_DIR / stamp / f"{rel}.{tag}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)

        def pull(rel: str) -> None:
            lp = SRC / rel
            lp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(work / rel, lp)
            pulled.append(rel)

        def push(rel: str) -> None:
            rp = work / rel
            rp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SRC / rel, rp)
            pushed.append(rel)

        for rel in sorted(set(local) | set(remote)):
            lh = _hash(local[rel]) if rel in local else None
            rh = _hash(remote[rel]) if rel in remote else None
            b = base.get(rel)
            if lh == rh:
                new_state[rel] = lh
            elif lh is None:
                pull(rel)
                new_state[rel] = rh
            elif rh is None:
                push(rel)
                new_state[rel] = lh
            elif rel in resolved:  # a human merged it here: this machine's version is the truth
                push(rel)
                new_state[rel] = lh
            elif b is not None and lh == b:  # only the repo changed it
                pull(rel)
                new_state[rel] = rh
            elif b is not None and rh == b:  # only this machine changed it
                push(rel)
                new_state[rel] = lh
            elif b is not None:  # both changed it: leave it for a human
                save_aside(remote[rel], rel, "repo")
                conflicts.append(rel)
                new_state[rel] = b
            else:  # no record (first run): newer side wins, loser saved aside
                remote_time = int(run("git", "log", "-1", "--format=%ct", "--", rel, cwd=work) or 0)
                if remote_time > local[rel].stat().st_mtime:
                    save_aside(local[rel], rel, "local")
                    pull(rel)
                    new_state[rel] = rh
                else:
                    save_aside(remote[rel], rel, "repo")
                    push(rel)
                    new_state[rel] = lh

        for rel in pulled:
            print(f"pulled    {rel}")
        for rel in pushed:
            print(f"pushed    {rel}")
        for rel in conflicts:
            print(f"CONFLICT  {rel}: changed here and in the repo; the repo's version is in drafts/{BACKUP_DIR}/{stamp}/")

        run("git", "add", "-A", cwd=work)
        if run("git", "status", "--porcelain", cwd=work):
            run("git", "-c", "user.name=gzchenhao", "-c", "user.email=haolu98@icloud.com",
                "commit", "-q", "-m", "sync drafts", cwd=work)
            run("git", "push", "-q", "origin", "main", cwd=work)
        state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        if not (pulled or pushed or conflicts):
            print("drafts and the private repo already agree")


if __name__ == "__main__":
    main()
