"""`ohp doctor` — answer "why does nothing happen?" from the one place we can still speak.

The failure this exists for: a user edits their MCP config, the client never starts the
server, and the only symptom is an assistant that appears not to know the tools exist.
When that happens OUR CODE NEVER RUNS, so every hint, error and diagnosis we have written
is unreachable. The terminal is the only channel we still own.

Three things go wrong in a new user's first ten minutes and all three look identical from
the chat window: `uv` is missing, the index is empty, or the server is configured but not
enabled. This separates them.

Honesty rule for this module: we can read config FILES, so we can say whether openhire is
configured. Most clients do not persist "the user flipped the enable switch" anywhere we
can read, so we must NOT claim to know that. A checker that guesses is worse than one that
says it cannot see.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# (label, path, whether the client is known to gate a newly added server behind an
# explicit enable/trust action). The gate flag drives what we tell the user to check next.
_MCP_KEY = "mcpServers"


@dataclass(frozen=True)
class ClientConfig:
    label: str
    path: Path
    needs_enabling: bool


def known_client_configs(home: Path | None = None) -> list[ClientConfig]:
    """Config files we know how to read, for the platform we are on."""
    home = home or Path.home()
    out: list[ClientConfig] = []

    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        out.append(ClientConfig("Claude Desktop", appdata / "Claude" / "claude_desktop_config.json", False))
        # The Microsoft Store build is sandboxed and keeps its config elsewhere.
        pkgs = home / "AppData" / "Local" / "Packages"
        if pkgs.is_dir():
            for pkg in pkgs.glob("*Claude*"):
                out.append(ClientConfig(
                    "Claude Desktop (Store)",
                    pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json",
                    False,
                ))
    elif sys.platform == "darwin":
        out.append(ClientConfig(
            "Claude Desktop",
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            False,
        ))

    out.append(ClientConfig("Cursor", home / ".cursor" / "mcp.json", True))
    out.append(ClientConfig("Windsurf", home / ".codeium" / "windsurf" / "mcp_config.json", False))
    out.append(ClientConfig("VS Code", home / ".vscode" / "mcp.json", True))
    out.append(ClientConfig("Claude Code", home / ".claude.json", False))
    return out


def _servers_in(path: Path) -> dict | None:
    """The config's server map, or None if the file is absent or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    servers: dict = {}
    for key in (_MCP_KEY, "servers"):  # VS Code uses "servers"
        found = data.get(key)
        if isinstance(found, dict):
            servers.update(found)
    # Claude Code keeps a server map PER PROJECT, not at the top level. Reading only the
    # top level reported "openhire is not configured" for a client where it plainly was.
    projects = data.get("projects")
    if isinstance(projects, dict):
        for proj in projects.values():
            if isinstance(proj, dict) and isinstance(proj.get(_MCP_KEY), dict):
                servers.update(proj[_MCP_KEY])
    return servers or None


def find_openhire(path: Path) -> tuple[str, str] | None:
    """Return (server name, command) if this config mentions openhire, else None."""
    servers = _servers_in(path)
    if not servers:
        return None
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        blob = " ".join(
            [str(name), str(spec.get("command", "")), *[str(a) for a in spec.get("args", []) or []]]
        ).lower()
        if "openhire" in blob or "ohp" in blob:
            cmd = " ".join(
                [str(spec.get("command", ""))] + [str(a) for a in (spec.get("args") or [])]
            ).strip()
            return name, cmd
    return None


@dataclass
class Finding:
    level: str  # ok | warn | fail
    text: str
    action: str | None = None


def run_checks(home: Path | None = None, now: dt.datetime | None = None) -> list[Finding]:
    """Every check, as data. The CLI only formats this."""
    from sqlalchemy import func, select

    from .db import Company, Job, init_db, session_scope

    now = now or dt.datetime.now(dt.timezone.utc)
    out: list[Finding] = []

    # 1. uv/uvx. NOT an unconditional requirement: it is only needed if a config actually
    #    invokes it. The maintainer's own machine has no uvx and works fine, because its
    #    config points at an installed `ohp`. Reporting a hard failure there would send
    #    someone to fix a prerequisite they do not have and do not need.
    configs = [c for c in known_client_configs(home) if c.path.exists()]
    hits = {c.label: find_openhire(c.path) for c in configs}
    uses_uvx = any(h and "uvx" in h[1].lower() for h in hits.values())
    uvx = shutil.which("uvx")
    if uvx:
        out.append(Finding("ok", f"uvx 已安装（{uvx}）"))
    elif uses_uvx:
        out.append(Finding(
            "fail", "配置里用了 uvx，但本机找不到它。客户端只会报「server failed to start」，没有别的线索。",
            "安装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh"
            "  ·  Windows: irm https://astral.sh/uv/install.ps1 | iex",
        ))
    else:
        out.append(Finding("ok", "没有 uvx，但你的配置也没用它，不影响。"))

    # 2. The index. "Empty" and "no matches" are the same sentence to a user.
    init_db()
    with session_scope() as s:
        live = s.scalar(select(func.count()).select_from(Job).where(Job.delisted_at.is_(None))) or 0
        companies = s.scalar(select(func.count()).select_from(Company)) or 0
        newest = s.scalar(select(func.max(Job.verified_at)))
    if live == 0:
        out.append(Finding(
            "fail", "本机没有职位索引，所以任何搜索都会返回空。",
            "跑 `ohp bootstrap` 下载公开快照（约 25 MB，无需注册），或直接 `ohp serve`，服务器会自己拉。",
        ))
    else:
        age = None
        if newest:
            stamp = newest if newest.tzinfo else newest.replace(tzinfo=dt.timezone.utc)
            age = (now - stamp).days
        aged = f"，核验于 {age} 天前" if age is not None else ""
        level = "warn" if (age is not None and age > 14) else "ok"
        out.append(Finding(
            level, f"索引就绪：{companies} 家公司 · {live:,} 条在架{aged}",
            "索引偏旧，跑 `ohp bootstrap --force` 拉一份新的。" if level == "warn" else None,
        ))

    # 3. Client configs. We can read the file; we usually CANNOT read whether the user
    #    enabled the server, so we say which clients gate it instead of guessing.
    configured = [c for c in configs if hits.get(c.label)]
    missing = [c for c in configs if not hits.get(c.label)]
    found_any = bool(configured)

    # Only nag about clients that lack it when NOTHING has it. Someone who set up Claude
    # Desktop does not need to be told that their unrelated editor is also not configured;
    # that turns a health check into a list of chores they never asked for.
    if found_any and missing:
        out.append(Finding("ok", "其他已安装的客户端没有配 openhire（不影响）："
                                 + "、".join(c.label for c in missing)))

    for cfg in configured:
        hit = hits[cfg.label]
        name, cmd = hit
        out.append(Finding("ok", f"{cfg.label} 已配置 openhire：{name} → {cmd or '(无命令)'}"))
        if cfg.needs_enabling:
            out.append(Finding(
                "warn",
                f"{cfg.label} 里新加的 server 通常要手动启用才会加载工具，而这个开关存在哪里我们读不到。",
                f"打开 {cfg.label} 的 MCP / 连接器设置，确认 openhire 的开关是打开的。",
            ))

    if not found_any:
        # Round 5: this fired on a machine where openhire WAS configured, in a client we
        # do not know about. "Not found in any known client" is true and reads as "you did
        # not install it". Name what was actually checked, and say the list is not the
        # world, so a reader with a different client knows the check simply cannot see it.
        checked = "、".join(c.label for c in known_client_configs(home)) or "（无）"
        present = "、".join(c.label for c in configs) or "一个都没有"
        out.append(Finding(
            "warn", f"在我认识的客户端配置里没找到 openhire。我查的是：{checked}；"
                    f"其中本机存在配置文件的：{present}。",
            "如果你用的是别的客户端（WorkBuddy、Cline、自研宿主等），这个检查看不到它，"
            "请直接在那个客户端里确认 openhire 是否已启用。"
            ' 要手动配置：{"mcpServers":{"openhire":{"command":"uvx","args":["openhire@latest","serve"]}}}',
        ))
    return out
