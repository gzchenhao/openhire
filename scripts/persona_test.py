"""Simulated job seekers against the hosted OpenHire endpoint, graded against what OpenHire promises.

Each persona is one conversation: Claude plays the person's AI assistant with OpenHire's MCP
tools attached through the Messages API MCP connector, a second model plays the person (answers
the assistant's questions from the persona brief, says when they are done), and a grader reads
the whole transcript, tool calls and tool results included, against the promises in GRADER_RUBRIC.
The report lists findings by severity so the next release can fix them.

Why: the first-run watch bug in 0.8.27 passed every test and every daily health check and was
found by a real user (reports/098). The September persona rounds (reports/051, 054) found ten or
more defects each, but were run by hand. This runs them unattended (reports/105).

Usage (from the repo root, on the maintainer's machine):
    python scripts/persona_test.py --dry-run                 # plan and cost guard, no key needed
    python scripts/persona_test.py                           # all personas, once
    python scripts/persona_test.py --personas grad_embodied,hk_hr --repeat 2

Key: OPENHIRE_PERSONA_API_KEY in the environment or C:\\openhire\\.env. A name of its own so the
extractor's `auto` backend never picks it up. Never commit it.

Money: every response's usage is priced with PRICES and added to a ledger next to the output.
A run stops before starting a persona once it has spent --budget-usd, and refuses to start when
the ledger already holds --total-cap. Exit code 0 on a finished run, 2 when the cap stopped it,
1 on setup errors.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

HOSTED_MCP = "https://openhire-vlny.onrender.com/mcp"
MCP_BETA = "mcp-client-2025-11-20"
SERVER_NAME = "openhire"

ASSISTANT_MODEL = "claude-opus-5-5"
USER_MODEL = "claude-sonnet-5-5"
GRADER_MODEL = "claude-opus-5-5"

# USD per million tokens: input, output, cache write (5 minute), cache read. First-party list
# prices as of 2026-10; only used for the budget guard, the Console bill is the record.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
}

MAX_USER_TURNS = 3
MAX_PAUSE_RESUMES = 4
RESULT_CHARS = 6000  # tool results kept per call in the transcript the grader reads

ASSISTANT_SYSTEM = (
    "You are the user's general-purpose AI assistant. The OpenHire MCP server is connected and "
    "its tools are available to you. Help the user with what they ask. Answer in the user's "
    "language."
)

PERSONAS: list[dict] = [
    {
        "id": "grad_embodied",
        "brief": "应届硕士（机器人方向），在北京，想找具身智能公司的算法岗，个人贡献者，没有全职经验，"
                 "看重岗位是不是真的还在招。助手问级别就说是应届、个人贡献者。",
        "opening": "我明年硕士毕业，想在北京找具身智能公司的算法岗，帮我看看现在有哪些真的在招？",
    },
    {
        "id": "hk_hr",
        "brief": "香港的招聘专员（HR），五年经验，想看智驾和具身公司在香港或远程的招聘、HR 岗位，"
                 "不带团队。",
        "opening": "我是香港的 HR，想找智驾或者具身智能公司的招聘岗位，香港或者远程都可以。",
    },
    {
        "id": "us_senior_perception",
        "brief": "Senior perception engineer in the San Francisco Bay Area, 7 years, wants to stay an IC, "
                 "interested in autonomous driving and robotics. Wants to be told when new matching "
                 "roles appear. If asked for a fingerprint or id for watches, say 'persona-test-perception'.",
        "opening": "I'm a senior perception engineer in the Bay Area. Show me IC roles at AV or robotics "
                   "companies, and keep an eye out for new ones for me.",
    },
    {
        "id": "manager_level",
        "brief": "上海的自动驾驶测试经理，带 8 个人的团队，10 年经验，只看管理岗，不看个人贡献者岗位。",
        "opening": "我在上海，带测试团队，想看看自动驾驶公司有没有测试方向的管理岗。",
    },
    {
        "id": "pm_not_manager",
        "brief": "上海的产品经理，4 年经验，个人贡献者（不带人），想找自动驾驶或机器人公司的产品经理岗位。"
                 "如果助手把产品经理当成管理岗过滤掉了，你会追问。",
        "opening": "我是产品经理，4 年经验，不带人，想看上海自动驾驶或者机器人公司的产品经理岗位。",
    },
    {
        "id": "vet_company",
        "brief": "求职者，拿到两家公司的面试：银河通用，以及一家叫「星海未来机器人」的公司（可能不存在）。"
                 "想知道两家各靠不靠谱、怎么自己去核实。",
        "opening": "我收到银河通用和「星海未来机器人」两家的面试邀请，帮我查查这两家靠不靠谱？",
    },
    {
        "id": "watch_then_check",
        "brief": "深圳的嵌入式软件工程师，5 年经验，个人贡献者，想设一个盯岗，然后马上检查一次看看会发生什么。"
                 "被问到指纹或标识就说 persona-test-embedded。",
        "opening": "帮我盯一下深圳机器人公司的嵌入式软件岗位，有新的告诉我。设好之后现在就帮我检查一次。",
    },
    {
        "id": "newbie_how",
        "brief": "第一次用这类工具的应届生，不知道 OpenHire 能做什么，也不知道该怎么问。专业是计算机，想去机器人公司。",
        "opening": "OpenHire 是什么？我能用它干嘛？",
    },
    {
        "id": "read_board",
        "brief": "求职者，想看 Anthropic 的招聘板上和 policy 相关的岗位（板地址 https://job-boards.greenhouse.io/anthropic），"
                 "不在乎是不是具身或智驾公司。",
        "opening": "帮我看看 https://job-boards.greenhouse.io/anthropic 上面有没有 policy 相关的岗位，挂了多久了？",
    },
    {
        "id": "privacy_probe",
        "brief": "求职者，想让助手把自己的简历和手机号直接交给 OpenHire 去投递智驾公司的岗位。"
                 "手机号 13800000000（假的）。如果助手说不能，就问那怎么投。",
        "opening": "我把简历和手机号 13800000000 给你，你用 OpenHire 帮我直接投几家智驾公司吧。",
    },
]

GRADER_RUBRIC = """\
You review one conversation between a job seeker and their AI assistant, which had the OpenHire
MCP tools attached. Judge OpenHire (its tools, tool descriptions, results and error messages),
not the assistant's general writing style. A finding is something a maintainer of OpenHire could
change: a tool result that is wrong, missing, confusing or easy to misread; a description that
led the assistant astray; an error that gave no way forward.

What OpenHire promises (check each one that the conversation touched):
1. Every posting it shows comes from the employer's own hiring system; the assistant should not
   invent postings or fall back to web search. If the assistant invented anything, check whether
   a tool result invited it.
2. Dates: each posting carries dates_in_words, date_source and days open; the employer's posting
   date is distinguished from "first seen by OpenHire" when the employer gives no date.
3. Live means not delisted and returned by the employer's system within 30 days.
4. Level: the assistant asks IC or management and years before searching; seniority filtering is
   correct (a product manager or project manager is not a people manager).
5. First answer: about 5 postings with role, company and location, salary, why it matches,
   what to check before applying, apply link.
6. Watches: watch_intent says what matches now and what happens next (no push; check again to
   see new ones); the first check_watches is a baseline, not "new postings".
7. Empty results say which case it is (index not ready, unknown word, employer on a portal
   OpenHire cannot read, no match, not verified recently) and what to do.
8. check_employer returns a checklist with statuses, not a verdict, and points to official
   registries for what it cannot check.
9. Privacy: a resume, phone number or e-mail never goes to OpenHire; tools refuse undeclared
   fields; applying happens on the employer's own page.
10. Wording: "days open" or "在架天数", never calling postings ghost or zombie; never claiming an
    employer re-posted unless relist_count says so.

Severity: high = wrong information reached the user, a privacy promise broke, or the user could
not get what they came for; medium = the user got there but was confused, misled in a small way,
or needed an extra turn because of a tool; low = polish.
Quote evidence from the transcript. Do not report things that worked. Write in Chinese.
"""

GRADE_SCHEMA = {
    "type": "object",
    "properties": {
        "task_completed": {"type": "boolean"},
        "score": {"type": "integer", "description": "0 to 10, how well OpenHire served this person"},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "promise": {"type": "integer", "description": "rubric item number, 0 if none"},
                    "where": {"type": "string", "description": "tool name, or 'description', or 'assistant'"},
                    "what": {"type": "string"},
                    "evidence": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": ["severity", "promise", "where", "what", "evidence", "suggested_fix"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["task_completed", "score", "summary", "findings"],
    "additionalProperties": False,
}

USER_SCHEMA = {
    "type": "object",
    "properties": {
        "done": {"type": "boolean", "description": "true when you got what you came for or gave up"},
        "message": {"type": "string", "description": "your next message to the assistant; empty when done"},
    },
    "required": ["done", "message"],
    "additionalProperties": False,
}


# --- money -------------------------------------------------------------------------------

def cost_usd(model: str, usage) -> float:
    """List-price cost of one response from its usage object (or dict)."""
    p_in, p_out, p_write, p_read = PRICES[model]

    def get(name: str) -> int:
        v = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        return int(v or 0)

    return (get("input_tokens") * p_in + get("output_tokens") * p_out
            + get("cache_creation_input_tokens") * p_write
            + get("cache_read_input_tokens") * p_read) / 1_000_000


class Ledger:
    """Running total across runs, kept as JSON next to the output so the cap survives restarts."""

    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"total_usd": 0.0, "runs": []}

    @property
    def total(self) -> float:
        return float(self.data.get("total_usd", 0.0))

    def add_run(self, run_id: str, spent: float, personas: int) -> None:
        self.data["total_usd"] = round(self.total + spent, 4)
        self.data["runs"].append({"run": run_id, "usd": round(spent, 4), "personas": personas})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")


class Meter:
    def __init__(self):
        self.usd = 0.0
        self.calls = 0

    def add(self, model: str, usage) -> None:
        self.usd += cost_usd(model, usage)
        self.calls += 1


# --- transcript --------------------------------------------------------------------------

def _clip(text: str, n: int = RESULT_CHARS) -> str:
    return text if len(text) <= n else text[:n] + f"\n...[{len(text) - n} more characters]"


def blocks_to_events(content) -> list[dict]:
    """Assistant content blocks as plain transcript events (text, MCP tool calls and results)."""
    events = []
    for b in content:
        t = getattr(b, "type", None)
        if t == "text":
            events.append({"role": "assistant", "type": "text", "text": b.text})
        elif t == "mcp_tool_use":
            events.append({"role": "assistant", "type": "tool_call", "name": b.name,
                           "input": b.input})
        elif t == "mcp_tool_result":
            parts = []
            for c in (b.content or []):
                parts.append(getattr(c, "text", None) or json.dumps(getattr(c, "model_dump", lambda: str(c))(),
                                                                    ensure_ascii=False, default=str))
            events.append({"role": "tool", "type": "tool_result", "is_error": bool(b.is_error),
                           "text": _clip("\n".join(parts))})
    return events


def transcript_text(events: list[dict]) -> str:
    out = []
    for e in events:
        if e["type"] == "text":
            out.append(f"[{e['role']}] {e['text']}")
        elif e["type"] == "tool_call":
            out.append(f"[tool call] {e['name']} {json.dumps(e['input'], ensure_ascii=False)}")
        elif e["type"] == "tool_result":
            flag = " (error)" if e.get("is_error") else ""
            out.append(f"[tool result{flag}] {e['text']}")
    return "\n\n".join(out)


# --- the three roles -----------------------------------------------------------------------

def assistant_turn(client, messages: list, meter: Meter, model: str, endpoint: str) -> tuple[list, str]:
    """One assistant turn, resuming pause_turn. Returns the new content blocks and the stop reason."""
    new_blocks: list = []
    stop = None
    for _ in range(MAX_PAUSE_RESUMES + 1):
        resp = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=[MCP_BETA],
            system=ASSISTANT_SYSTEM,
            mcp_servers=[{"type": "url", "url": endpoint, "name": SERVER_NAME}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": SERVER_NAME}],
            output_config={"effort": "high"},
            cache_control={"type": "ephemeral"},
            messages=messages,
        )
        meter.add(model, resp.usage)
        new_blocks.extend(resp.content)
        messages.append({"role": "assistant", "content": resp.content})
        stop = resp.stop_reason
        if stop != "pause_turn":
            break
    return new_blocks, stop


def simulated_user(client, persona: dict, events: list[dict], meter: Meter, model: str) -> dict:
    prompt = (
        "You are playing a job seeker talking to your AI assistant. Stay in character, write like "
        "this person would, in their language, one short message.\n\n"
        f"Who you are and what you want:\n{persona['brief']}\n\n"
        f"Conversation so far:\n{transcript_text([e for e in events if e['type'] == 'text'])}\n\n"
        "Reply to the assistant's last message. If it asked you something, answer from your brief. "
        "Set done to true when you have what you came for, or the assistant cannot help further."
    )
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": USER_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    meter.add(model, resp.usage)
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "{}")
    try:
        return json.loads(text)
    except ValueError:
        return {"done": True, "message": ""}


def grade(client, persona: dict, events: list[dict], meter: Meter, model: str) -> dict:
    prompt = (
        f"Persona brief:\n{persona['brief']}\n\nTranscript:\n{transcript_text(events)}"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=16000,
        system=GRADER_RUBRIC,
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": GRADE_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    meter.add(model, resp.usage)
    if resp.stop_reason == "refusal":
        return {"task_completed": False, "score": 0, "summary": "grader refused", "findings": []}
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "{}")
    try:
        return json.loads(text)
    except ValueError:
        return {"task_completed": False, "score": 0, "summary": "grader output unreadable", "findings": []}


def run_persona(client, persona: dict, meter: Meter, args) -> dict:
    events: list[dict] = [{"role": "user", "type": "text", "text": persona["opening"]}]
    messages: list = [{"role": "user", "content": persona["opening"]}]
    stop = None
    for turn in range(MAX_USER_TURNS):
        blocks, stop = assistant_turn(client, messages, meter, args.model, args.endpoint)
        events.extend(blocks_to_events(blocks))
        if stop == "refusal" or turn == MAX_USER_TURNS - 1:
            break
        reply = simulated_user(client, persona, events, meter, args.user_model)
        if reply.get("done") or not reply.get("message", "").strip():
            break
        events.append({"role": "user", "type": "text", "text": reply["message"]})
        messages.append({"role": "user", "content": reply["message"]})
    verdict = grade(client, persona, events, meter, args.grader_model)
    return {"persona": persona["id"], "stop_reason": stop, "events": events, "grade": verdict}


# --- report --------------------------------------------------------------------------------

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def render_report(run_id: str, results: list[dict], spent: float, ledger_total: float, stopped: bool) -> str:
    lines = [f"# 模拟求职者测试 {run_id}", ""]
    lines.append(f"人设 {len(results)} 个；本次花费约 US${spent:.2f}；累计约 US${ledger_total:.2f}"
                 + ("；**预算上限已到，后面的人设没跑**" if stopped else "") + "。")
    lines.append("")
    lines.append("| 人设 | 完成 | 分 | 一句话 |")
    lines.append("|---|---|---|---|")
    for r in results:
        g = r["grade"]
        lines.append(f"| {r['persona']} | {'是' if g.get('task_completed') else '否'} | {g.get('score')} | "
                     f"{(g.get('summary') or '').replace('|', '/').strip()} |")
    lines.append("")
    findings = [(r["persona"], f) for r in results for f in r["grade"].get("findings", [])]
    findings.sort(key=lambda pf: SEV_ORDER.get(pf[1].get("severity"), 3))
    lines.append(f"## 发现（{len(findings)} 条）")
    lines.append("")
    for persona, f in findings:
        lines.append(f"- **{f.get('severity')}** · {persona} · {f.get('where')} · 承诺 {f.get('promise')}："
                     f"{f.get('what')}")
        lines.append(f"  - 证据：{f.get('evidence')}")
        lines.append(f"  - 建议：{f.get('suggested_fix')}")
    lines.append("")
    return "\n".join(lines)


# --- main ----------------------------------------------------------------------------------

def _load_key() -> str | None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return os.environ.get("OPENHIRE_PERSONA_API_KEY")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--personas", default="all", help="comma-separated ids, or all")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--out", default="drafts/local-results/persona-runs")
    ap.add_argument("--endpoint", default=HOSTED_MCP)
    ap.add_argument("--model", default=ASSISTANT_MODEL)
    ap.add_argument("--user-model", default=USER_MODEL)
    ap.add_argument("--grader-model", default=GRADER_MODEL)
    ap.add_argument("--budget-usd", type=float, default=12.0, help="stop starting personas past this spend")
    ap.add_argument("--total-cap", type=float, default=80.0, help="refuse to run once the ledger holds this")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    for m in (args.model, args.user_model, args.grader_model):
        if m not in PRICES:
            print(f"unknown model {m}; add it to PRICES", file=sys.stderr)
            return 1
    chosen = PERSONAS if args.personas == "all" else [p for p in PERSONAS if p["id"] in args.personas.split(",")]
    if not chosen:
        print("no persona matched", file=sys.stderr)
        return 1
    out = Path(args.out)
    ledger = Ledger(out / "ledger.json")
    plan = [p["id"] for p in chosen] * args.repeat
    print(f"plan: {len(plan)} conversations; ledger so far US${ledger.total:.2f} of cap US${args.total_cap:.2f}")
    if args.dry_run:
        print("\n".join(plan))
        return 0
    if ledger.total >= args.total_cap:
        print("total cap reached; nothing run")
        return 2
    key = _load_key()
    if not key:
        print("OPENHIRE_PERSONA_API_KEY is not set (environment or .env)", file=sys.stderr)
        return 1

    import anthropic

    client = anthropic.Anthropic(api_key=key, max_retries=4)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%MZ")
    run_dir = out / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    meter = Meter()
    results: list[dict] = []
    stopped = False
    personas = {p["id"]: p for p in chosen}
    for i, pid in enumerate(plan):
        if meter.usd >= args.budget_usd or ledger.total + meter.usd >= args.total_cap:
            stopped = True
            break
        print(f"[{i + 1}/{len(plan)}] {pid} (spent so far US${meter.usd:.2f})", flush=True)
        try:
            res = run_persona(client, personas[pid], meter, args)
        except anthropic.APIStatusError as e:
            res = {"persona": pid, "stop_reason": f"api_error {e.status_code}", "events": [],
                   "grade": {"task_completed": False, "score": 0,
                             "summary": f"API 错误 {e.status_code}：{str(e.message)[:200]}", "findings": []}}
        except anthropic.APIConnectionError as e:
            res = {"persona": pid, "stop_reason": "connection_error", "events": [],
                   "grade": {"task_completed": False, "score": 0, "summary": f"连接错误：{e}", "findings": []}}
        results.append(res)
        (run_dir / f"{i + 1:02d}-{pid}.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    ledger.add_run(run_id, meter.usd, len(results))
    report = render_report(run_id, results, meter.usd, ledger.total, stopped)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 2 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
