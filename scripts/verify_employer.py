"""Check an employer's self-reported identity materials before registering a roster.

The applicant fills the 公司信息 sheet of docs/openhire-岗位表.xlsx (or passes the same
fields on the command line); this script runs every check that can run without a human
and prints what is left for one: the registry lookups behind captchas and the callback.

    python scripts/verify_employer.py --xlsx "岗位表.xlsx" --sender-domain example-robotics.cn
    python scripts/verify_employer.py --name "示例机器人有限公司" --uscc 91110000MA01ABCD2X \
        --domain example-robotics.cn --icp 京ICP备12345678号 --phone 010-12345678 \
        --phone-page https://www.example-robotics.cn/contact --sender-domain example-robotics.cn \
        --footprint https://www.example-robotics.cn/product --footprint https://github.com/example

What it checks by itself (reports/064):
  * the 统一社会信用代码 is well-formed and its check digit is right (GB 32100-2015);
  * the corporate email's domain is the company's domain, not a look-alike;
  * the company's homepage carries the ICP 备案号 the applicant gave and the company name;
  * how old the domain is (RDAP registration date) and how long the site has been seen
    (earliest Wayback Machine capture), so a shell bought last month stands out;
  * the public phone number really appears on the page the applicant pointed at, which
    must be on the company's own domain, so the callback goes to the company, not to the
    sender;
  * the industry-footprint links resolve and at least one is on the company's own domain.

What it cannot do and says so: the 工商 lookup (gsxt.gov.cn) and the ICP lookup
(beian.miit.gov.cn) sit behind captchas, and the callback is a phone call. It prints the
prefilled URLs and the sentence to put in the registry's `verification` field once a
human has done them. Nothing here is a verdict on the employer's intentions; it
establishes that a real registered company in our field is asking, and that the
person asking can be reached through that company.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from urllib.parse import urlparse

import httpx

USCC_ALPHABET = "0123456789ABCDEFGHJKLMNPQRTUWXY"
USCC_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30]
ICP_RE = re.compile(
    r"[京津沪渝冀晋蒙辽吉黑苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云藏陕甘青宁新]ICP[备证]\s*\d{6,9}\s*号(?:\s*-\s*\d+)?"
)
MIN_DOMAIN_AGE_DAYS = 180

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


# --- pure checks -------------------------------------------------------------------------
def uscc_check_digit(prefix17: str) -> str:
    total = sum(USCC_ALPHABET.index(ch) * w for ch, w in zip(prefix17, USCC_WEIGHTS))
    return USCC_ALPHABET[(31 - total % 31) % 31]


def uscc_valid(code: str | None) -> tuple[bool, str]:
    """GB 32100-2015: 18 characters from a 31-symbol alphabet, last one a check digit."""
    code = (code or "").strip().upper()
    if len(code) != 18:
        return False, "统一社会信用代码应为 18 位"
    if any(ch not in USCC_ALPHABET for ch in code):
        return False, "含有非法字符（不含 I、O、S、V、Z）"
    if uscc_check_digit(code[:17]) != code[17]:
        return False, "校验位不对，多半是抄错或编造"
    return True, "格式与校验位正确（这只证明它像一个真代码，登记记录仍要去公示系统查）"


def normalise_domain(value: str | None) -> str:
    v = (value or "").strip().lower()
    if "://" in v:
        v = urlparse(v).hostname or ""
    v = v.split("/")[0]
    return v[4:] if v.startswith("www.") else v


def same_domain(host: str | None, domain: str) -> bool:
    h = normalise_domain(host)
    return bool(h) and (h == domain or h.endswith("." + domain))


def sender_matches(sender_domain: str | None, domain: str) -> tuple[bool, str]:
    s = normalise_domain(sender_domain)
    if not s:
        return False, "没有发件域名"
    if s == domain or s.endswith("." + domain):
        return True, f"发件域名 {s} 属于 {domain}"
    return False, f"发件域名 {s} 不是 {domain}；相似域名是冒充的常用手法，按不通过处理"


# --- network checks (one plain GET each; a failure is a WARN, never a retry with a disguise) ---
def _get(url: str, timeout: float = 20.0) -> httpx.Response | None:
    try:
        return httpx.get(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError:
        return None


def homepage_check(domain: str, icp: str | None, name: str | None) -> dict:
    r = _get(f"https://{domain}/")
    if r is None or r.status_code != 200:
        return {"status": "WARN", "note": f"https://{domain}/ 打不开或非 200，备案号与公司名无法自动核对"}
    html = r.text
    found = ICP_RE.findall(html)
    out = {"icp_on_page": [re.sub(r"\s+", "", f) for f in found], "name_on_page": bool(name and name in html)}
    want = re.sub(r"\s+", "", icp or "")
    if want:
        out["icp_matches"] = want in out["icp_on_page"]
        out["status"] = "PASS" if out["icp_matches"] else "FAIL"
        out["note"] = ("首页页脚有申请人给的备案号" if out["icp_matches"]
                       else f"首页没有申请人给的备案号 {want}；页脚备案号 {out['icp_on_page'] or '无'}")
    else:
        out["status"] = "WARN"
        out["note"] = "未提供备案号（海外公司可空）；首页备案号：" + (", ".join(out["icp_on_page"]) or "无")
    if name and not out["name_on_page"]:
        out["note"] += "；首页正文没有出现公司全称（常见于只写简称的站，人工看一眼）"
    return out


def domain_age(domain: str) -> dict:
    r = _get(f"https://rdap.org/domain/{domain}")
    if r is None or r.status_code != 200:
        return {"status": "WARN", "note": "RDAP 查不到注册日期（.cn 常见），改看互联网档案馆首次抓取"}
    try:
        events = r.json().get("events", [])
        reg = next((e["eventDate"] for e in events if e.get("eventAction") == "registration"), None)
    except (ValueError, KeyError, TypeError):
        reg = None
    if not reg:
        return {"status": "WARN", "note": "RDAP 返回里没有注册日期"}
    registered = dt.datetime.fromisoformat(reg.replace("Z", "+00:00")).date()
    age = (dt.date.today() - registered).days
    return {"status": "PASS" if age >= MIN_DOMAIN_AGE_DAYS else "FAIL",
            "registered": registered.isoformat(), "age_days": age,
            "note": f"域名注册于 {registered}，{age} 天" + ("" if age >= MIN_DOMAIN_AGE_DAYS else f"，不足 {MIN_DOMAIN_AGE_DAYS} 天，像新壳")}


def wayback_first_capture(domain: str) -> dict:
    r = _get(f"https://web.archive.org/cdx/search/cdx?url={domain}&output=json&limit=1&fl=timestamp&filter=statuscode:200")
    if r is None or r.status_code != 200:
        return {"status": "WARN", "note": "互联网档案馆查不到"}
    try:
        rows = r.json()
        ts = rows[1][0] if len(rows) > 1 else None
    except (ValueError, IndexError, TypeError):
        ts = None
    if not ts:
        return {"status": "WARN", "note": "互联网档案馆没有这个站的抓取记录（新站或被 robots 挡住）"}
    first = dt.datetime.strptime(ts[:8], "%Y%m%d").date()
    age = (dt.date.today() - first).days
    return {"status": "PASS" if age >= MIN_DOMAIN_AGE_DAYS else "FAIL", "first_capture": first.isoformat(),
            "age_days": age, "note": f"互联网档案馆首次抓取 {first}，{age} 天前"}


def phone_on_page(phone: str | None, page: str | None, domain: str) -> dict:
    if not phone or not page:
        return {"status": "FAIL", "note": "没有公开电话或它所在的页面网址"}
    if not same_domain(urlparse(page).hostname, domain):
        return {"status": "FAIL", "note": f"电话所在页面 {page} 不在 {domain} 域名下；回拨号码必须来自公司自己的站"}
    r = _get(page)
    if r is None or r.status_code != 200:
        return {"status": "WARN", "note": "电话页面打不开，人工到官网找号码"}
    digits = re.sub(r"\D", "", phone)
    page_digits = re.sub(r"\D", "", r.text)
    ok = len(digits) >= 7 and digits in page_digits
    return {"status": "PASS" if ok else "FAIL",
            "note": "号码出现在公司自己的页面上，回拨它" if ok else "页面上没有这个号码；回拨时用页面上的号码，不用邮件里的"}


def footprints(links: list[str], domain: str) -> dict:
    checked = []
    for u in [x for x in links if x]:
        r = _get(u)
        checked.append({"url": u, "ok": bool(r is not None and r.status_code == 200),
                        "own_domain": same_domain(urlparse(u).hostname, domain)})
    if not checked:
        return {"status": "FAIL", "note": "没有行业足迹链接", "links": []}
    resolving = [c for c in checked if c["ok"]]
    status = "PASS" if resolving and any(c["own_domain"] for c in resolving) else ("WARN" if resolving else "FAIL")
    return {"status": status, "links": checked,
            "note": "链接可打开；是不是智驾 / 具身 / AI 基础设施的真足迹，要人工看" if resolving else "链接都打不开"}


# --- sheet input -------------------------------------------------------------------------
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


# --- the run ------------------------------------------------------------------------------
def run(info: dict, sender_domain: str | None) -> dict:
    domain = normalise_domain(info.get("domain"))
    report: dict = {"domain": domain, "checks": {}}
    if not domain:
        report["checks"]["domain"] = {"status": "FAIL", "note": "没有官网域名"}
        return report
    ok, note = uscc_valid(info.get("uscc"))
    report["checks"]["uscc"] = {"status": "PASS" if ok else ("WARN" if info.get("foreign_reg") else "FAIL"), "note": note}
    ok, note = sender_matches(sender_domain, domain)
    report["checks"]["sender_domain"] = {"status": "PASS" if ok else "FAIL", "note": note}
    report["checks"]["homepage"] = homepage_check(domain, info.get("icp"), info.get("name"))
    report["checks"]["domain_age"] = domain_age(domain)
    report["checks"]["site_history"] = wayback_first_capture(domain)
    report["checks"]["phone"] = phone_on_page(info.get("phone"), info.get("phone_page"), domain)
    report["checks"]["footprints"] = footprints([info.get("footprint1"), info.get("footprint2")], domain)
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
    """The sentence that goes into SELF_REPORTED_EMPLOYERS[...].verification once the manual
    steps are done. It names what was checked, by whom and when, and never a person's name."""
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
