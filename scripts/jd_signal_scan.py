"""What embodied-AI employers write into their JDs: paper / degree / school / years / real-robot signals.

    python3 scripts/jd_signal_scan.py ~/.openhire/openhire.db            # prints the tables
    python3 scripts/jd_signal_scan.py ~/.openhire/openhire.db --json     # machine-readable

A maintainer's measurement over the public snapshot (reports/078): every live posting of
the employers listed in EMBODIED below is scanned for a few keyword families, on the
title plus the JD text as the employer's own system returned it. Nothing is inferred: a
posting "mentions papers" when one of the PAPER patterns occurs in its text, no more. The
employer list is a judgement call (robots and embodied AI as the main business; lidar
makers, autonomous-driving fleets and AI labs are left out) and is printed with the
figures so anyone can disagree with it precisely.

Numbers for public copy are taken from this script's output on a dated snapshot, never
from memory (CLAUDE.md, 文案规矩 1).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import statistics
import sys

# Main business is robots / embodied AI. Domestic (CN) and overseas, by companies.id.
EMBODIED_CN = [
    "unitree", "galaxea", "ubtrobot", "dobot", "jaka", "mechmind", "megarobo", "pudutech", "hairobotics",
    "siasun", "yijiahe", "paxini", "galbot", "robotera", "fftai", "geekplus", "keenon",
    "astribot", "magiclab",  # added 2026-10-20 (reports/084); absent from earlier snapshots
]
EMBODIED_OVERSEAS = [
    "figureai", "agilityrobotics", "skildai", "apptronik", "carbonrobotics", "pathrobotics", "dexterity",
    "fieldai", "ambirobotics", "1x", "dynarobotics", "generalist", "standardbots", "cobot",
    "physicalintelligence", "robotec-ai", "flexion-robotics", "andromeda-robotics", "agile-robots", "palrobotics",
]
EMBODIED = EMBODIED_CN + EMBODIED_OVERSEAS

# Keyword families. Latin tokens are matched on word boundaries, case-insensitively; CJK
# strings as substrings. A family hits when ANY pattern occurs in title + JD.
FAMILIES = {
    "paper": [
        r"\b(corl|icra|iros|neurips|nips|icml|iclr|cvpr|iccv|eccv|aaai|rss|ra-l|t-ro)\b",
        r"\bscience robotics\b", r"\bpublications?\b", r"\bpublished\b", r"\bpeer[- ]reviewed\b",
        r"\bfirst[- ]author\b", r"顶会", r"顶级会议", r"论文", r"学术成果", r"发表",
    ],
    "phd": [r"\bph\.?d\b", r"\bdoctoral\b", r"\bdoctorate\b", r"博士"],
    "school": [r"\b985\b", r"\b211\b", r"双一流", r"名校", r"知名高校", r"重点高校", r"重点大学",
               r"\btop[- ](tier )?(university|universities|school|schools|program|programs)\b", r"\bqs\b"],
    "new_grad": [r"应届", r"校招", r"校园招聘", r"\bnew[- ]grads?\b", r"\bnew graduates?\b", r"\brecent graduates?\b",
                 r"\bentry[- ]level\b"],
    "intern": [r"实习", r"\binterns?\b", r"\binternship\b"],
    "real_robot": [r"真机", r"实机", r"实物", r"\breal[- ]robots?\b",
                   r"\breal[- ]world (robots?|deployments?|environments?|conditions|settings|data|systems?|tasks?|testing|performance)\b",
                   r"\bphysical (robots?|systems?|hardware)\b",
                   r"\bon[- ]robot\b", r"\bon hardware\b", r"机器人本体", r"实际机器人", r"现场调试", r"真实环境", r"真实场景"],
    "frontier": [r"\bvla\b", r"vision[- ]language[- ]action", r"\bworld models?\b", r"世界模型", r"\bfoundation models?\b",
                 r"基础模型", r"大模型", r"\bllms?\b", r"\bvlms?\b", r"diffusion polic", r"imitation learning", r"模仿学习",
                 r"强化学习", r"reinforcement learning", r"\bsim[- ]to[- ]real\b", r"\bsim2real\b"],
    "reproduce": [r"复现", r"\breproduc(e|ing|tion)\b", r"\bre-?implement", r"\bopen[- ]source\b", r"开源"],
}
# Minimum years of experience stated in the JD, e.g. 3年以上 / 5+ years / 3-5 years / at least 2 years.
YEARS = [
    re.compile(r"(\d{1,2})\s*(?:\+|年以上|年及以上|年或以上|年以上经验|年相关|年以上相关)"),
    re.compile(r"(\d{1,2})\s*(?:-|–|~|到|至)\s*\d{1,2}\s*(?:年|years?)"),
    re.compile(r"(\d{1,2})\+?\s*(?:years?|yrs?)\b"),
    re.compile(r"(?:at least|minimum of|minimum|min\.?)\s*(\d{1,2})\s*(?:years?|yrs?)"),
    re.compile(r"(\d{1,2})\s*年"),
]
OPTIONAL = re.compile(r"优先|加分|bonus|preferred|a plus|nice[- ]to[- ]have|plus:|desirable|ideally", re.I)
RESEARCH_TITLE = re.compile(r"research|scientist|算法|研究|machine learning|\bml\b|learning engineer|ai engineer|perception|policy|"
                            r"foundation model|vla|planning|控制算法|感知|决策|规划|模型", re.I)

SNAPSHOT_DAY = dt.date(2026, 10, 13)  # the snapshot's generation day; days_open counts to it


def _compiled():
    return {k: [re.compile(p, re.I) for p in pats] for k, pats in FAMILIES.items()}


def min_years(text: str) -> int | None:
    found = []
    for rx in YEARS:
        for m in rx.finditer(text):
            try:
                n = int(m.group(1))
            except (ValueError, IndexError):
                continue
            if 1 <= n <= 20:
                found.append(n)
    return min(found) if found else None


def scan(db_path: str) -> dict:
    con = sqlite3.connect(db_path)
    rx = _compiled()
    q = ("select j.id, j.company_id, c.name, j.title, coalesce(j.description_raw,''), j.posted_at, j.role_family "
         "from jobs j join companies c on c.id=j.company_id where j.delisted_at is null and j.company_id in (%s)"
         % ",".join("?" * len(EMBODIED)))
    rows = []
    for jid, cid, cname, title, jd, posted, fam in con.execute(q, EMBODIED):
        text = (title or "") + "\n" + (jd or "")
        low = text.lower()
        hits = {k: any(r.search(low) for r in pats) for k, pats in rx.items()}
        paper_optional = None
        if hits["paper"]:
            # The sentence around the first paper match: a bonus ("优先 / 加分 / preferred / plus")
            # or a requirement. 优先 and 加分 are how Chinese JDs mark nice-to-haves.
            m = next(r.search(low) for r in rx["paper"] if r.search(low))
            a, b = max(0, m.start() - 80), min(len(low), m.end() + 80)
            window = low[a:b]
            paper_optional = bool(OPTIONAL.search(window))
        year = None
        days = None
        if posted:
            try:
                d = dt.datetime.fromisoformat(str(posted).replace("Z", "+00:00")).date()
                year = d.year
                days = (SNAPSHOT_DAY - d).days
            except ValueError:
                pass
        rows.append({
            "id": jid, "company": cid, "company_name": cname, "region": "cn" if cid in EMBODIED_CN else "overseas",
            "research_title": bool(RESEARCH_TITLE.search(title or "")), "role_family": fam,
            "has_jd": len(jd or "") > 200, "min_years": min_years(low), "posted_year": year, "days_open": days,
            "paper_optional": paper_optional, **hits,
        })

    def pct(sub, key):
        return round(100 * sum(1 for r in sub if r[key]) / len(sub)) if sub else None

    def block(sub):
        fam = {k: pct(sub, k) for k in FAMILIES}
        yrs = [r["min_years"] for r in sub if r["min_years"] is not None]
        out = {
            "postings": len(sub),
            "with_jd": sum(1 for r in sub if r["has_jd"]),
            **{f"pct_{k}": v for k, v in fam.items()},
            "pct_states_min_years": round(100 * len(yrs) / len(sub)) if sub else None,
            "pct_min_years_ge3": round(100 * sum(1 for y in yrs if y >= 3) / len(sub)) if sub else None,
            "pct_min_years_ge5": round(100 * sum(1 for y in yrs if y >= 5) / len(sub)) if sub else None,
            "pct_paper_and_ge3_years": round(100 * sum(1 for r in sub if r["paper"] and (r["min_years"] or 0) >= 3) / len(sub)) if sub else None,
            "pct_paper_no_years": round(100 * sum(1 for r in sub if r["paper"] and r["min_years"] is None) / len(sub)) if sub else None,
        }
        papers = [r for r in sub if r["paper"]]
        out["paper_postings"] = len(papers)
        out["pct_of_paper_marked_optional"] = round(100 * sum(1 for r in papers if r["paper_optional"]) / len(papers)) if papers else None
        out["pct_of_paper_without_years"] = round(100 * sum(1 for r in papers if r["min_years"] is None) / len(papers)) if papers else None
        days_paper = [r["days_open"] for r in sub if r["paper"] and r["days_open"] is not None]
        days_other = [r["days_open"] for r in sub if not r["paper"] and r["days_open"] is not None]
        out["median_days_open_paper"] = round(statistics.median(days_paper)) if days_paper else None
        out["median_days_open_no_paper"] = round(statistics.median(days_other)) if days_other else None
        return out

    by_company = []
    for cid in EMBODIED:
        sub = [r for r in rows if r["company"] == cid]
        if sub:
            by_company.append({"company": cid, "name": sub[0]["company_name"], "region": sub[0]["region"],
                               "postings": len(sub), "pct_paper": pct(sub, "paper"), "pct_phd": pct(sub, "phd"),
                               "pct_real_robot": pct(sub, "real_robot"), "pct_frontier": pct(sub, "frontier")})
    by_company.sort(key=lambda b: -b["postings"])
    years = {}
    for y in (2024, 2025, 2026):
        sub = [r for r in rows if r["posted_year"] == y]
        if sub:
            years[str(y)] = block(sub)
    older = [r for r in rows if r["posted_year"] and r["posted_year"] < 2024]
    if older:
        years["before_2024"] = block(older)
    return {
        "snapshot_day": SNAPSHOT_DAY.isoformat(),
        "employers": {"cn": EMBODIED_CN, "overseas": EMBODIED_OVERSEAS},
        "all": block(rows),
        "cn": block([r for r in rows if r["region"] == "cn"]),
        "overseas": block([r for r in rows if r["region"] == "overseas"]),
        "research_titles": block([r for r in rows if r["research_title"]]),
        "other_titles": block([r for r in rows if not r["research_title"]]),
        "research_cn": block([r for r in rows if r["research_title"] and r["region"] == "cn"]),
        "research_overseas": block([r for r in rows if r["research_title"] and r["region"] == "overseas"]),
        "by_posted_year": years,
        "by_company": by_company,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: jd_signal_scan.py <openhire.db> [--json]", file=sys.stderr)
        return 64
    out = scan(argv[1])
    if "--json" in argv:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    keys = ["postings", "with_jd", "pct_paper", "pct_phd", "pct_school", "pct_new_grad", "pct_intern", "pct_states_min_years",
            "pct_min_years_ge3", "pct_min_years_ge5", "pct_paper_and_ge3_years", "pct_paper_no_years", "pct_real_robot",
            "pct_frontier", "pct_reproduce", "paper_postings", "pct_of_paper_marked_optional", "pct_of_paper_without_years",
            "median_days_open_paper", "median_days_open_no_paper"]
    for name in ("all", "cn", "overseas", "research_titles", "other_titles", "research_cn", "research_overseas"):
        b = out[name]
        print(f"== {name}: " + "  ".join(f"{k}={b[k]}" for k in keys))
    for y, b in out["by_posted_year"].items():
        print(f"== posted {y}: " + "  ".join(f"{k}={b[k]}" for k in keys))
    print("== by company (postings, %paper, %phd, %real_robot, %frontier)")
    for b in out["by_company"]:
        print(f"   {b['name'][:28]:28s} {b['region']:8s} {b['postings']:4d}  {b['pct_paper']:3d}  {b['pct_phd']:3d}  {b['pct_real_robot']:3d}  {b['pct_frontier']:3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
