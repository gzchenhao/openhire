"""scripts/run_local_tasks.py: the cloud session's checks run on the maintainer's machine.

Pinned here: only the two read-only subcommands can be queued (the task file is data, not
a shell), a task's JSON is parsed out of whatever else the CLI printed, and a failed task
is recorded and does not stop the batch.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("run_local_tasks", ROOT / "scripts" / "run_local_tasks.py")
rlt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rlt)


class _R:
    def __init__(self, rc, out, err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_only_the_two_read_only_subcommands_can_be_queued(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps([{"id": "a b/c", "kind": "check-company", "args": ["OKX", "--domain", "okx.com"]}]), encoding="utf-8")
    assert rlt.load_tasks(p) == [{"id": "a_b_c", "kind": "check-company", "args": ["OKX", "--domain", "okx.com"]}]
    p.write_text(json.dumps([{"id": "x", "kind": "seed", "args": []}]), encoding="utf-8")
    with pytest.raises(SystemExit):
        rlt.load_tasks(p)
    p.write_text(json.dumps([{"id": "x", "kind": "read-board", "args": [1]}]), encoding="utf-8")
    with pytest.raises(SystemExit):
        rlt.load_tasks(p)


def test_run_task_parses_the_json_and_a_failure_is_recorded_not_fatal():
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        return _R(0, "banner noise\n" + json.dumps({"company": "OKX", "checks": [{"status": "verified", "label": "x", "note": "y"}]}))

    out = rlt.run_task({"id": "t1", "kind": "check-company", "args": ["OKX"]}, ohp=["ohp"], runner=fake)
    assert seen["cmd"] == ["ohp", "check-company", "OKX", "--json"]
    assert out["ok"] and out["result"]["company"] == "OKX"
    bad = rlt.run_task({"id": "t2", "kind": "read-board", "args": ["u"]}, ohp=["ohp"], runner=lambda cmd, **kw: _R(2, "", "boom"))
    assert not bad["ok"] and bad["stderr_tail"] == "boom"
    lines = rlt.summarise(out) + rlt.summarise(bad)
    assert any("verified" in line for line in lines) and any("失败" in line for line in lines)


def test_main_writes_one_file_per_task_and_a_summary(tmp_path, monkeypatch):
    tasks = tmp_path / "local-tasks.json"
    tasks.write_text(json.dumps([{"id": "one", "kind": "read-board", "args": ["https://jobs.lever.co/x"]}]), encoding="utf-8")
    monkeypatch.setattr(rlt, "run_task", lambda task, ohp=None, runner=None: {
        "id": task["id"], "kind": task["kind"], "args": task["args"], "started_at": "t", "ok": True, "returncode": 0,
        "result": {"vendor": "lever", "tenant": "x", "count_on_board": 1, "total_matching": 1, "postings": []}, "stderr_tail": ""})
    out = tmp_path / "results"
    rlt.main(["--tasks", str(tasks), "--out", str(out)])
    assert (out / "one.json").exists() and list(out.glob("summary-*.md"))
