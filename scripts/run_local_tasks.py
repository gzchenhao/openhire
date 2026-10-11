"""Run OpenHire checks on this machine for a cloud session, and hand the results back.

The cloud container cannot reach RDAP, the Wayback Machine, employer homepages or the OFAC
lists (reports/068, 070), so a cloud session writes the checks it needs into the private
repo as `local-tasks.json`, the drafts sync pulls that file into drafts/, this script runs
each task here with the local `ohp` and writes the answers to drafts/local-results/, and
the next sync pushes them back for the cloud session to read.

    .venv\\Scripts\\python.exe scripts\\run_local_tasks.py --sync    # pull, run, push

Only two subcommands can be queued, `check-company` and `read-board`: the task file is
data, not a shell, and nothing in it is executed except as arguments to those two.

Task file shape (a JSON list):
    [{"id": "okx-domain", "kind": "check-company", "args": ["OKX", "--domain", "okx.com"]},
     {"id": "uipath-hk", "kind": "read-board", "args": ["https://jobs.ashbyhq.com/uipath", "--location", "Hong Kong"]}]
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "drafts"
ALLOWED = {"check-company", "read-board"}
DEFAULT_TASKS = DRAFTS / "local-tasks.json"
DEFAULT_OUT = DRAFTS / "local-results"


def ohp_path() -> list[str]:
    for cand in (ROOT / ".venv" / "Scripts" / "ohp.exe", ROOT / ".venv" / "bin" / "ohp"):
        if cand.exists():
            return [str(cand)]
    return [sys.executable, "-m", "openhire.cli"]


def load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path}: expected a JSON list of tasks")
    tasks = []
    for i, t in enumerate(data):
        if not isinstance(t, dict) or t.get("kind") not in ALLOWED:
            raise SystemExit(f"{path}: task {i} must have kind in {sorted(ALLOWED)}; got {t!r}")
        args = t.get("args") or []
        if not all(isinstance(a, str) for a in args):
            raise SystemExit(f"{path}: task {i}: args must be strings")
        tid = str(t.get("id") or f"task-{i + 1}")
        tid = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tid)
        tasks.append({"id": tid, "kind": t["kind"], "args": list(args)})
    return tasks


def run_task(task: dict, ohp: list[str] | None = None, runner=subprocess.run) -> dict:
    cmd = [*(ohp or ohp_path()), task["kind"], *task["args"], "--json"]
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    try:
        r = runner(cmd, capture_output=True, text=True, encoding="utf-8", timeout=900)
        rc, out, err = r.returncode, r.stdout or "", r.stderr or ""
    except Exception as exc:  # a missing ohp, a timeout: the task reports it, the batch goes on
        rc, out, err = -1, "", f"{type(exc).__name__}: {exc}"
    result = None
    start = out.find("{")
    if start >= 0:
        try:
            result = json.loads(out[start:])
        except ValueError:
            result = None
    return {"id": task["id"], "kind": task["kind"], "args": task["args"], "started_at": started,
            "ok": rc == 0 and result is not None, "returncode": rc, "result": result,
            "stderr_tail": err[-2000:]}


def summarise(outcome: dict) -> list[str]:
    res = outcome.get("result") or {}
    lines = [f"## {outcome['id']} · {outcome['kind']} {' '.join(outcome['args'])}", ""]
    if not outcome["ok"]:
        lines += [f"失败（returncode {outcome['returncode']}）：{outcome['stderr_tail'].strip()[-400:]}", ""]
        return lines
    if outcome["kind"] == "check-company":
        lines.append(f"公司：{res.get('company') or ''}  域名：{res.get('domain') or '（未知）'}")
        for item in res.get("checks", []):
            lines.append(f"- {item.get('status')} · {item.get('label')}：{item.get('note')}")
    else:
        lines.append(f"{res.get('vendor')}:{res.get('tenant')}  板上 {res.get('count_on_board')} 条，匹配 {res.get('total_matching')} 条")
        for p in res.get("postings", []):
            lines.append(f"- {p.get('datePosted') or '----------'}  {p.get('title')}  [{p.get('location') or ''}]  {p.get('apply_channel')}")
    lines.append("")
    return lines


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    tasks_path = Path(argv[argv.index("--tasks") + 1]) if "--tasks" in argv else DEFAULT_TASKS
    out_dir = Path(argv[argv.index("--out") + 1]) if "--out" in argv else DEFAULT_OUT
    sync = "--sync" in argv
    backup = ROOT / "scripts" / "backup_drafts.py"
    if sync:
        subprocess.run([sys.executable, str(backup)], check=False)
    if not tasks_path.exists():
        raise SystemExit(f"no task file at {tasks_path}; nothing to run")
    tasks = load_tasks(tasks_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    summary = [f"# 本地任务结果 {stamp}", "", f"任务文件：{tasks_path.name}，{len(tasks)} 个任务", ""]
    for task in tasks:
        outcome = run_task(task)
        (out_dir / f"{task['id']}.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
        summary += summarise(outcome)
        print(f"{'ok  ' if outcome['ok'] else 'FAIL'} {task['id']}")
    (out_dir / f"summary-{stamp}.md").write_text("\n".join(summary), encoding="utf-8")
    print(f"results in {out_dir}")
    if sync:
        subprocess.run([sys.executable, str(backup)], check=False)


if __name__ == "__main__":
    main()
