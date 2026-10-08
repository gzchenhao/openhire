"""Check an employer's self-reported identity materials before registering a roster.

The applicant fills the 公司信息 sheet of docs/openhire-岗位表.xlsx (or passes the same
fields on the command line); this script runs every check that can run without a human
and prints what is left for one: the registry lookups behind captchas and the callback.

    python scripts/verify_employer.py --xlsx "岗位表.xlsx" --sender-domain example-robotics.cn
    python scripts/verify_employer.py --name "示例机器人有限公司" --uscc 91110000MA01ABCD2X \\
        --domain example-robotics.cn --icp 京ICP备12345678号 --phone 010-12345678 \\
        --phone-page https://www.example-robotics.cn/contact --sender-domain example-robotics.cn \\
        --footprint https://www.example-robotics.cn/product --footprint https://github.com/example

The checks themselves live in `openhire.verify.checks` (the same code the `check_employer`
MCP tool uses for seekers, reports/064 and 065). This script grades them PASS / WARN / FAIL
for a maintainer and prints the prefilled URLs for the three things only a human can do:
the 工商 lookup (gsxt.gov.cn), the ICP lookup (beian.miit.gov.cn) and the callback.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

from openhire.verify import checks as _c

uscc_check_digit = _c.uscc_check_digit
uscc_valid = _c.uscc_valid
normalise_domain = _c.normalise_domain
same_domain = _c.same_domain
sender_matches = _c.sender_matches
homepage_check = _c.homepage_check
domain_age = _c.domain_age
wayback_first_capture = _c.wayback_first_capture
footprints = _c.footprints

COMPANY_FIELDS = {
    "公司全称": "name",
    "统一社会信用代码": "uscc",
    "海外注册号及注册地（海外公司填）": "foreign_reg",
    "官网域名": "domain",
    "ICP 备案号（国内公司填）": "icp",
    "官网上公开电话所在页面网址": "phone_page",
    "公开电话": "phone",
    "行业足迹链接一（产品页 / GitHub / 论文 / 报道）": "footprint1",
    "行业足迹链接二": "footprint2",
    "经办人职务": "role",
}

_GRADE = {"verified": "PASS", "not_verified": "FAIL", "unavailable": "WARN", "not_applicable": "WARN"}


def _graded(d: dict) -> dict:
    out = dict(d)
    out["status"] = _GRADE.get(d.get("status", ""), "WARN")
    return out


def phone_on_page(phone, page, domain) -> dict:
    return _graded(_c.phone_on_page(phone, page, domain))


def read_company_sheet(path: pathlib.Path) -> dict:
    import openpyxl  # dev dependency only

    wb = openpyxl.load_workbook(path, data_only=True)
    if "公司信息" not in wb.sheetnames:
        raise SystemExit("表里没有「公司信息」页；请用 docs/openhire-岗位表.xlsx 最新模板")
    ws = wb["公司信息"]
    out: dict = {}
    for row in ws.iter_rows(values_only=True):
        if not row or row[0] is None:
            continue
        key = str(row[0]).strip()
        val = row[1] if len(row) > 1 else None
        if key in COMPANY_FIELDS:
            out[COMPANY_FIELDS[key]] = str(val).strip() if val not in (None, "") else None
    return out


def run(info: dict, sender_domain: str | None) -> dict:
    domain = normalise_domain(info.get("domain"))
    report: dict = {"domain": domain, "checks": {}}
    if not domain:
        report["checks"]["domain"] = {"status": "FAIL", "note": "没有官网域名"}
        report["automatic_verdict"] = "FAIL"
        report["failed"] = ["domain"]
        report["manual"] = []
        return report
    ok, note = uscc_valid(info.get("uscc"))
    report["checks"]["uscc"] = {"status": "PASS" if ok else ("WARN" if info.get("foreign_reg") else "FAIL"), "note": note}
    ok, note = sender_matches(sender_domain, domain)
    report["checks"]["sender_domain"] = {"status": "PASS" if ok else "FAIL", "note": note}
    report["checks"]["homepage"] = _graded(homepage_check(domain, info.get("icp"), info.get("name")))
    report["checks"]["domain_age"] = _graded(domain_age(domain))
    report["checks"]["site_history"] = _graded(wayback_first_capture(domain))
    report["checks"]["phone"] = phone_on_page(info.get("phone"), info.get("phone_page"), domain)
    report["checks"]["footprints"] = _graded(footprints([info.get("footprint1"), info.get("footprint2")], domain))
    report["manual"] = [
        f"工商登记：到 https://www.gsxt.gov.cn/ 按全称「{info.get('name') or '?'}」查：成立日期、经营状态、经营范围是否在智驾 / 具身 / AI 基础设施，统一社会信用代码是否为 {info.get('uscc') or '?'}",
        f"ICP 备案：到 https://beian.miit.gov.cn/ 查域名 {domain}，主办单位名称应等于公司全称",
        f"回拨：拨打公司自己页面上的号码 {info.get('phone') or '?'}，确认「{info.get('role') or '经办人'}」确实发了岗位表",
        "行业足迹：打开两个链接，判断它真在我们的三个方向里（这一步靠人）",
    ]
    fails = [k for k, v in report["checks"].items() if v.get("status") == "FAIL"]
    report["automatic_verdict"] = "FAIL" if fails else "PASS_PENDING_MANUAL"
    report["failed"] = fails
    return report


def verification_sentence(report: dict, info: dict, who: str, when: str) -> str:
    """The sentence for SELF_REPORTED_EMPLOYERS[...].verification once the manual steps are
    done: what was checked, by whom and when, never a person's name."""
    c = report["checks"]
    parts = [f"gsxt record checked {when}", f"ICP {info.get('icp') or 'n/a'} on homepage: {c['homepage'].get('status')}",
             f"domain registered {c['domain_age'].get('registered', 'unknown')}",
             f"first archived {c['site_history'].get('first_capture', 'unknown')}",
             f"callback to the public number {when} by {who}", "sender on corporate domain"]
    return "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--xlsx", type=pathlib.Path)
    ap.add_argument("--name"); ap.add_argument("--uscc"); ap.add_argument("--foreign-reg")
    ap.add_argument("--domain"); ap.add_argument("--icp"); ap.add_argument("--phone"); ap.add_argument("--phone-page")
    ap.add_argument("--footprint", action="append", default=[]); ap.add_argument("--role")
    ap.add_argument("--sender-domain", required=True, help="the domain the email actually came from")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    a = ap.parse_args(argv)
    info = read_company_sheet(a.xlsx) if a.xlsx else {}
    for k in ("name", "uscc", "foreign_reg", "domain", "icp", "phone", "phone_page", "role"):
        v = getattr(a, k)
        if v:
            info[k] = v
    if a.footprint:
        info["footprint1"] = a.footprint[0]
        info["footprint2"] = a.footprint[1] if len(a.footprint) > 1 else info.get("footprint2")
    report = run(info, a.sender_domain)
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["automatic_verdict"] != "FAIL" else 1
    print(f"域名 {report['domain']}")
    for k, v in report["checks"].items():
        print(f"  [{v.get('status', '?'):4}] {k}: {v.get('note', '')}")
    print(f"自动检查结论：{report['automatic_verdict']}" + (f"（未通过：{', '.join(report['failed'])}）" if report['failed'] else ""))
    print("还要人做的：")
    for m in report["manual"]:
        print("  - " + m)
    if report["automatic_verdict"] != "FAIL":
        print("人工都过了之后，登记表 verification 字段可写：")
        print("  " + verification_sentence(report, info, "maintainer", dt.date.today().isoformat()))
    return 0 if report["automatic_verdict"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
