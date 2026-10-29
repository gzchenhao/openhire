"""scripts/persona_test.py without the network: a fake client stands in for the Messages API,
so the loop, the transcript, the money guard and the report are checked for free (reports/105)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("persona_test", ROOT / "scripts" / "persona_test.py")
pt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pt)


def _usage(i=1000, o=200):
    return NS(input_tokens=i, output_tokens=o, cache_creation_input_tokens=0, cache_read_input_tokens=0)


class FakeClient:
    """Assistant: one tool call then text. User: answers once then done. Grader: one finding."""

    def __init__(self):
        self.user_calls = 0
        self.beta = NS(messages=NS(create=self._assistant))
        self.messages = NS(create=self._plain)
        self.assistant_kwargs = []

    def _assistant(self, **kw):
        self.assistant_kwargs.append(kw)
        content = [
            NS(type="mcp_tool_use", id="t1", name="search_jobs", server_name="openhire",
               input={"query": "embodied", "seniority": "ic"}),
            NS(type="mcp_tool_result", tool_use_id="t1", is_error=False,
               content=[NS(type="text", text="x" * (pt.RESULT_CHARS + 50))]),
            NS(type="text", text="这里是 5 条岗位。"),
        ]
        return NS(content=content, stop_reason="end_turn", usage=_usage())

    def _plain(self, **kw):
        schema = kw["output_config"]["format"]["schema"]
        if schema is pt.USER_SCHEMA:
            self.user_calls += 1
            reply = {"done": self.user_calls > 1, "message": "我是应届，个人贡献者"}
            return NS(content=[NS(type="text", text=json.dumps(reply, ensure_ascii=False))],
                      stop_reason="end_turn", usage=_usage(500, 50))
        grade = {"task_completed": True, "score": 7, "summary": "基本找到",
                 "findings": [{"severity": "medium", "promise": 2, "where": "search_jobs",
                               "what": "日期没说清", "evidence": "…", "suggested_fix": "…"}]}
        return NS(content=[NS(type="text", text=json.dumps(grade, ensure_ascii=False))],
                  stop_reason="end_turn", usage=_usage(3000, 400))


def _args(**kw):
    base = dict(model=pt.ASSISTANT_MODEL, user_model=pt.USER_MODEL, grader_model=pt.GRADER_MODEL,
                endpoint=pt.HOSTED_MCP)
    base.update(kw)
    return NS(**base)


def test_personas_are_well_formed_and_unique():
    ids = [p["id"] for p in pt.PERSONAS]
    assert len(ids) == len(set(ids)) >= 8
    for p in pt.PERSONAS:
        assert p["brief"].strip() and p["opening"].strip()


def test_cost_uses_all_four_token_kinds():
    u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
         "cache_creation_input_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000}
    assert pt.cost_usd("claude-opus-5-5", u) == 4.0 + 20.0 + 5.0 + 0.2


def test_one_conversation_end_to_end_with_mcp_connector():
    client, meter = FakeClient(), pt.Meter()
    res = pt.run_persona(client, pt.PERSONAS[0], meter, _args())
    kw = client.assistant_kwargs[0]
    assert kw["betas"] == [pt.MCP_BETA]
    assert kw["mcp_servers"][0]["url"] == pt.HOSTED_MCP
    assert kw["tools"] == [{"type": "mcp_toolset", "mcp_server_name": pt.SERVER_NAME}]
    kinds = [e["type"] for e in res["events"]]
    assert kinds[:4] == ["text", "tool_call", "tool_result", "text"]
    assert "more characters" in res["events"][2]["text"]          # long results are clipped
    assert res["events"][4]["role"] == "user"                      # simulated user answered once
    assert res["grade"]["findings"][0]["promise"] == 2
    assert meter.calls == 2 + 2 + 1 and meter.usd > 0              # 2 assistant, 2 user, 1 grader


def test_pause_turn_is_resumed_and_appended_once_each():
    calls = []

    def create(**kw):
        calls.append(len(kw["messages"]))
        stop = "pause_turn" if len(calls) == 1 else "end_turn"
        return NS(content=[NS(type="text", text=str(len(calls)))], stop_reason=stop, usage=_usage())

    client = NS(beta=NS(messages=NS(create=create)))
    messages = [{"role": "user", "content": "hi"}]
    blocks, stop = pt.assistant_turn(client, messages, pt.Meter(), pt.ASSISTANT_MODEL, pt.HOSTED_MCP)
    assert stop == "end_turn" and len(blocks) == 2 and calls == [1, 2] and len(messages) == 3


def test_ledger_cap_refuses_and_budget_stops(tmp_path):
    out = tmp_path / "runs"
    ledger = pt.Ledger(out / "ledger.json")
    ledger.add_run("r0", 80.0, 3)
    assert pt.main(["--out", str(out), "--total-cap", "80"]) == 2       # nothing run, no key needed
    assert pt.Ledger(out / "ledger.json").total == 80.0


def test_dry_run_needs_no_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENHIRE_PERSONA_API_KEY", raising=False)
    assert pt.main(["--dry-run", "--out", str(tmp_path), "--personas", "hk_hr,newbie_how", "--repeat", "2"]) == 0
    assert "4 conversations" in capsys.readouterr().out


def test_report_sorts_findings_and_says_when_capped():
    results = [{"persona": "a", "grade": {"task_completed": True, "score": 8, "summary": "ok",
                                          "findings": [{"severity": "low", "promise": 10, "where": "x",
                                                        "what": "low one", "evidence": "", "suggested_fix": ""},
                                                       {"severity": "high", "promise": 1, "where": "y",
                                                        "what": "high one", "evidence": "", "suggested_fix": ""}]}}]
    text = pt.render_report("r1", results, 3.2, 10.0, stopped=True)
    assert text.index("high one") < text.index("low one")
    assert "预算上限已到" in text and "US$3.20" in text


def test_key_name_is_not_the_extractor_key():
    """The extractor's auto backend reads ANTHROPIC_API_KEY; this script must not share it."""
    src = (ROOT / "scripts" / "persona_test.py").read_text(encoding="utf-8")
    assert 'os.environ.get("OPENHIRE_PERSONA_API_KEY")' in src
    assert 'environ.get("ANTHROPIC_API_KEY")' not in src


def test_warm_up_polls_healthz_until_200():
    calls, sleeps = [], []

    class R:
        def __init__(self, status): self.status = status
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(req, timeout):
        calls.append(req.full_url)
        if len(calls) < 3:
            raise OSError("asleep")
        return R(200)

    assert pt.warm_up(pt.HOSTED_MCP, sleep=sleeps.append, opener=opener) is True
    assert calls[0] == "https://openhire-vlny.onrender.com/healthz" and len(sleeps) == 2


def test_warm_up_gives_up_after_timeout():
    def opener(req, timeout):
        raise OSError("down")
    assert pt.warm_up(pt.HOSTED_MCP, timeout_s=0, sleep=lambda s: None, opener=opener) is False


def test_only_mcp_connection_400_is_retried():
    assert pt._is_mcp_connection_error(NS(status_code=400, message="mcp_servers[0] 'openhire': Connection error while communicating with MCP server."))
    assert not pt._is_mcp_connection_error(NS(status_code=400, message="max_tokens too large"))
    assert not pt._is_mcp_connection_error(NS(status_code=401, message="MCP server"))


def test_local_backend_runs_tools_here_and_returns_results_in_one_message():
    class Local:
        instructions = "ask level first"
        tools = [{"name": "search_jobs", "description": "d", "input_schema": {"type": "object"}}]
        calls = []

        def call(self, name, arguments):
            self.calls.append((name, arguments))
            if name == "boom":
                raise RuntimeError("bad")
            return '{"results": []}', False

    seen = []

    def create(**kw):
        seen.append(kw)
        if len(seen) == 1:
            content = [NS(type="tool_use", id="a", name="search_jobs", input={"seniority": "ic"}),
                       NS(type="tool_use", id="b", name="boom", input={})]
            return NS(content=content, stop_reason="tool_use", usage=_usage())
        return NS(content=[NS(type="text", text="done")], stop_reason="end_turn", usage=_usage())

    local = Local()
    messages = [{"role": "user", "content": "hi"}]
    events, stop = pt.assistant_turn_local(NS(messages=NS(create=create)), messages, pt.Meter(), pt.ASSISTANT_MODEL, local)
    assert stop == "end_turn" and len(seen) == 2
    assert "ask level first" in seen[0]["system"] and seen[0]["tools"] == local.tools
    results = messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"] and results[1]["is_error"] is True
    assert [e["type"] for e in events] == ["tool_call", "tool_result", "tool_call", "tool_result", "text"]
