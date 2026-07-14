"""Terminal output styled to the 「哨兵」design system.

Symbol system (design_refs/OpenHire v0.1 哨兵.dc.html):
    $   command        green   #4ADE87
    ✓   success        green   #4ADE87
    ?   confirm        amber   #E5B85C
    ▸   output         muted   #5E6B62
    #   privacy note   dim     #3E4A42 / #5E6B62
    ⬥   notification   green   bold
Errors: an ERR_UPPER_SNAKE code + one plain-language sentence, in red #E07A6B.
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.theme import Theme

# Design tokens.
GREEN = "#4ADE87"
AMBER = "#E5B85C"
RED = "#E07A6B"
MUTED = "#9AA69D"
DIM = "#5E6B62"
TEXT = "#E9EEE9"

_theme = Theme(
    {
        "cmd": f"bold {GREEN}",
        "ok": GREEN,
        "ask": AMBER,
        "out": DIM,
        "note": DIM,
        "notif": f"bold {GREEN}",
        "err": f"bold {RED}",
        "errmsg": RED,
        "muted": MUTED,
        "text": TEXT,
        "accent": GREEN,
        "risk": AMBER,
    }
)

console = Console(theme=_theme, highlight=False)
err_console = Console(theme=_theme, stderr=True, highlight=False)


def cmd(text: str) -> None:
    console.print(f"[cmd]$[/] [text]{text}[/]")


def ok(text: str) -> None:
    console.print(f"[ok]✓[/] {text}")


def ask_line(text: str) -> None:
    console.print(f"[ask]?[/] {text}")


def out(text: str) -> None:
    console.print(f"[out]▸[/] [out]{text}[/]")


def note(text: str) -> None:
    console.print(f"[note]#[/] [note]{text}[/]")


def notif(text: str) -> None:
    console.print(f"[notif]⬥ {text}[/]")


def error(code: str, message: str) -> None:
    """ERR_UPPER_SNAKE + a plain sentence, to stderr."""
    err_console.print(f"[err]{code}[/] [errmsg]{message}[/]")


def confirm(prompt: str, default_yes: bool = True, assume_yes: bool = False) -> bool:
    """A [Y/n] confirmation whose text carries the privacy note (per design)."""
    suffix = "[Y/n]" if default_yes else "[y/N]"
    if assume_yes:
        console.print(f"[ask]?[/] {prompt} {suffix} [ok]y[/]")
        return True
    if not sys.stdin.isatty():
        # Non-interactive without --yes: refuse state-changing action safely.
        return False
    console.print(f"[ask]?[/] {prompt} {suffix} ", end="")
    try:
        resp = input().strip().lower()
    except EOFError:
        return default_yes
    if not resp:
        return default_yes
    return resp in ("y", "yes")


def rule(text: str = "") -> None:
    console.rule(f"[muted]{text}[/]" if text else "", style=DIM)
