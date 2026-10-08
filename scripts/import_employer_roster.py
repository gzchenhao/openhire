"""Turn an employer's spreadsheet into `employers/<slug>.json` (maintainer tool).

Usage (after scripts/verify_employer.py and the manual steps it lists, never before):

    python scripts/import_employer_roster.py --xlsx "岗位表.xlsx" --slug example-robotics \
        --name "示例机器人 Example Robotics" --domain example-robotics.cn \
        --careers-url https://www.example-robotics.cn/careers --verified-on 2026-10-08

Then declare the employer in `src/openhire/ats/self_reported.py` (SELF_REPORTED_EMPLOYERS)
and commit both. The sheet is the one at docs/openhire-岗位表.xlsx: one row per posting,
columns 职位名称 / 工作城市 / 发布日期 / 投递链接或投递邮箱 / 薪资范围 / 岗位描述.

Nothing personal is read: the sheet carries postings, not people. A column that looks
like a person's contact (手机, 微信, 联系人) is refused rather than copied.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

COLUMNS = ["职位名称", "工作城市", "发布日期", "投递链接或投递邮箱", "薪资范围", "岗位描述"]
REFUSED = ("手机", "微信", "联系人", "身份证", "电话")

from openhire.verify.checks import RED_FLAGS, email_on_domain, red_flags_in  # noqa: E402,F401


def _num(s: str, unit: str) -> int:
    v = float(s)
    if unit in ("k", "K", "千"):
        v *= 1000
    elif unit == "万":
        v *= 10000
    return int(round(v))


def parse_salary(text: str | None) -> dict:
    """'20k-35k/月' -> monthly CNY 20000..35000; '30万-50万/年' -> annual. Anything else -> {}."""
    if not text:
        return {}
    m = _SALARY.search(str(text))
    if not m:
        return {}
    lo = _num(m.group("lo"), m.group("lok") or m.group("hik"))
    hi = _num(m.group("hi"), m.group("hik") or m.group("lok"))
    if lo <= 0 or hi < lo:
        return {}
    period = "annual" if ("年" in str(text) or "/y" in str(text).lower()) else "monthly"
    return {"salary_min": lo, "salary_max": hi, "salary_currency": "CNY", "salary_period": period}


def _date(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip().replace("/", "-").replace(".", "-")
    try:
        return dt.date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None


def row_to_posting(row: dict, slug: str, domain: str = "") -> dict | None:
    """One sheet row -> one roster posting, or None (with a reason printed) when unusable."""
    title = re.sub(r"\s+", " ", str(row.get("职位名称") or "")).strip()
    posted = _date(row.get("发布日期"))
    if not title or not posted:
        print(f"  跳过：缺职位名称或发布日期 -> {row}", file=sys.stderr)
        return None
    flags = red_flags_in(title, row.get("岗位描述"), row.get("薪资范围"), row.get("工作城市"))
    if flags:
        print(f"  拒绝：「{title}」命中骗局招聘的特征词 {flags}", file=sys.stderr)
        return None
    contact = str(row.get("投递链接或投递邮箱") or "").strip()
    posting: dict = {
        "title": title,
        "location": str(row.get("工作城市") or "").strip() or None,
        "posted_at": posted,
        "description": str(row.get("岗位描述") or "").strip(),
    }
    if "@" in contact and not contact.lower().startswith("http"):
        if domain and not email_on_domain(contact, domain):
            print(f"  「{title}」的投递邮箱 {contact} 不在 {domain} 域名下，不收录该邮箱（候选人会被送到招聘页）", file=sys.stderr)
        else:
            posting["apply_email"] = contact
    elif contact:
        posting["apply_url"] = contact
    posting.update(parse_salary(row.get("薪资范围")))
    posting["id"] = hashlib.sha1(
        f"{slug}|{title}|{posting['location'] or ''}".encode("utf-8")
    ).hexdigest()[:12]
    return posting


def build_roster(rows: list[dict], *, slug: str, name: str, domain: str,
                 careers_url: str, verified_on: str, verification: str = "") -> dict:
    for col in (c for r in rows for c in r):
        if any(bad in str(col) for bad in REFUSED):
            raise SystemExit(f"拒绝导入：表里有疑似个人联系方式的列「{col}」，岗位表只放岗位，不放人")
    if not verification.strip():
        raise SystemExit("缺 --verification：先跑 scripts/verify_employer.py，把人工核过的那句话填进来")
    postings = [p for p in (row_to_posting(r, slug, domain) for r in rows) if p]
    return {
        "id": slug, "name": name, "domain": domain, "careers_url": careers_url,
        "verified_on": verified_on, "verification": verification, "postings": postings,
    }


def read_xlsx(path: pathlib.Path) -> list[dict]:
    import openpyxl  # dev dependency only; the server never needs it

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["岗位"] if "岗位" in wb.sheetnames else wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h or "").strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not any(v not in (None, "") for v in r):
            continue
        out.append({header[i]: r[i] for i in range(min(len(header), len(r)))})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--xlsx", required=True, type=pathlib.Path)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--careers-url", required=True)
    ap.add_argument("--verified-on", default=dt.date.today().isoformat())
    ap.add_argument("--verification", required=True,
                    help="what was checked, by whom and when (the sentence scripts/verify_employer.py prints)")
    ap.add_argument("--out-dir", default=pathlib.Path("employers"), type=pathlib.Path)
    a = ap.parse_args(argv)
    if not a.careers_url.startswith("https://"):
        raise SystemExit("careers_url 必须是 https")
    roster = build_roster(read_xlsx(a.xlsx), slug=a.slug, name=a.name, domain=a.domain,
                          careers_url=a.careers_url, verified_on=a.verified_on,
                          verification=a.verification)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    out = a.out_dir / f"{a.slug}.json"
    out.write_text(json.dumps(roster, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"写入 {out}：{len(roster['postings'])} 条岗位。下一步：在 ats/self_reported.py 的 "
          f"SELF_REPORTED_EMPLOYERS 里登记 {a.slug}，两处一起提交。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
