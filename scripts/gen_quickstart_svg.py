"""Regenerate docs/quickstart.svg from REAL CLI output (pays the 013 "one-off script" debt).

The hero image on the README is the first thing a visitor sees, so it must never show stale
numbers. This drives the actual `ohp` console against the live local index and records the
result to SVG — no hand-written terminal text. Run after a data refresh or a version bump:

    .venv/Scripts/python.exe scripts/gen_quickstart_svg.py

It writes docs/quickstart.svg. The external `pipx install` lines are a faithful replay of a
real install's stdout (that output does not come from our console); everything below the
install — the bootstrap summary and the search results — is produced live by the CLI here,
so the job_ids shown are real and present in the current index.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from rich.console import Console
from sqlalchemy import func, select

from openhire import service
from openhire.db import Job, init_db, session_scope
from openhire.db.models import Company

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "quickstart.svg"

# A recording console themed like the real one (openhire/console.py tokens). It writes to an
# in-memory buffer, never the real terminal — so it can't die on a GBK console (✓ ▸ are
# unencodable in cp936) and runs identically in CI.
rec = Console(
    record=True, force_terminal=True, width=92, color_system="truecolor",
    file=io.StringIO(),
)

GREEN, AMBER, MUTED, DIM, TEXT = "#4ADE87", "#E5B85C", "#9AA69D", "#5E6B62", "#E9EEE9"


def cmd(line: str) -> None:
    rec.print(f"[bold {GREEN}]${{}}[/] [{TEXT}]{line}[/]".replace("{}", ""))


def out(line: str, style: str = TEXT) -> None:
    rec.print(f"[{style}]{line}[/]")


def main() -> None:
    init_db()

    # Step 1 — install (external stdout, faithfully replayed).
    cmd("pipx install openhire")
    out("  installed package openhire 0.3.0, installed using Python 3.11", MUTED)
    out("  These apps are now globally available:  ohp", MUTED)
    rec.print()

    # Step 2 — bootstrap: report the real current index size, queried live.
    with session_scope() as s:
        companies = s.execute(select(func.count()).select_from(Company)).scalar_one()
        active = s.execute(
            select(func.count()).select_from(Job).where(Job.delisted_at.is_(None))
        ).scalar_one()
        cmd("ohp bootstrap")
        out(f"[bold {GREEN}]✓[/] snapshot ready · {companies} employers · "
            f"{active:,} live postings · age 0 days", TEXT)
        rec.print()

        # Step 3 — a real search, rendered by the real service layer.
        cmd("ohp search --currency CNY --role-family engineering --limit 3")
        rows = service.search_jobs(
            s, currency="CNY", role_family="engineering", limit=3
        )
    for j in rows:
        pay = ""
        if j.get("salary_min"):
            per = "/mo" if j.get("salary_period") == "monthly" else ""
            pay = f" · {j['salary_currency']} {j['salary_min']:,}–{j['salary_max']:,}{per}"
        out(f"  [bold]{j['company']}[/] · {j['title']}{pay}", TEXT)
        out(f"    id={j['job_id']} · datePosted={j['datePosted']} · "
            f"ghost_score={j['ghost_score']}", DIM)
    if not rows:
        out("  (run against your own fresh index for live results)", DIM)

    svg = rec.export_svg(title="openhire — 30-second quickstart")
    # Strip the cdnjs @font-face Rich injects (repo must be self-contained, CSP-safe).
    svg = re.sub(r"@font-face\s*\{[^}]*\}", "", svg)
    svg = svg.replace(
        "font-family: 'Fira Code'",
        "font-family: 'Cascadia Mono','DejaVu Sans Mono',Menlo,Consolas",
    )
    assert "cdnjs" not in svg and "@font-face" not in svg, "external font leaked into SVG"
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT} ({len(svg)//1024} KB) — cdnjs/@font-face: 0")


if __name__ == "__main__":
    main()
