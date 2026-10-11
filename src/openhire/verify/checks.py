"""Facts about an employer that the employer did not supply.

These checks serve two callers with the same code: the maintainer verifying a
self-reported roster (scripts/verify_employer.py) and the `check_employer` MCP tool a job
seeker asks "is this company what it says it is?". Every function returns a small dict
with a `status` the caller can print as-is:

    verified        the fact was confirmed from the named source at the named time
    not_verified    the source answered and did not confirm it
    unavailable     the source could not be reached or carries no record (never a verdict)
    not_applicable  the check does not apply to this employer

Network functions make exactly one plain GET each. A failure is `unavailable`, never a
retry with a different client identity (CLAUDE.md: being blocked means stop).
"""

from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlparse

import httpx

from .. import config

USCC_ALPHABET = "0123456789ABCDEFGHJKLMNPQRTUWXY"
USCC_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30]
ICP_RE = re.compile(
    r"[京津沪渝冀晋蒙辽吉黑苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云藏陕甘青宁新]ICP[备证]\s*\d{6,9}\s*号(?:\s*-\s*\d+)?"
)
MIN_DOMAIN_AGE_DAYS = 180

# The shapes recruitment scams take (the 缅北 playbook: a high-paid job abroad, flights and
# board paid, no experience needed, "customer service" or "typist" roles, pay by the day).
# A real robotics or autonomous-driving role never needs these words (reports/064).
RED_FLAGS = (
    "境外", "海外高薪", "柬埔寨", "缅甸", "缅北", "迪拜", "菲律宾", "包机票", "包吃住", "日结", "周结",
    "高薪诚聘", "无需经验", "不限经验", "不限学历", "打字员", "网络推广", "博彩", "彩票", "电销",
    "电话销售", "刷单", "急招", "签证办理", "护照", "出国务工", "月入过万", "轻松",
    "no experience", "visa provided", "flights paid", "typing job", "daily pay",
    # The same lures in traditional characters, as Hong Kong and Taiwan ads write them
    # (reports/068). Words whose traditional form equals the simplified one are not repeated.
    "包機票", "免費機票", "免费机票", "包食宿", "日結", "週結", "高薪誠聘", "無需經驗", "不限經驗",
    "不限學歷", "打字員", "網絡推廣", "電銷", "電話銷售", "刷單", "簽證辦理", "護照", "出國務工",
    "月入過萬", "輕鬆",
    # Hong Kong Police / Security Bureau job-scam markers (reports/068): money asked up front,
    # no interview, contact only through a messaging app.
    "押金", "保证金", "保證金", "培训费", "培訓費", "无需面试", "無需面試", "telegram", "whatsapp only",
)

# Hosts that belong to a recruiting vendor, never to the employer: a careers_url on one of
# these says nothing about the employer's own domain.
VENDOR_HOST_SUFFIXES = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "zhiye.com", "mokahr.com", "jobs.feishu.cn",
    "workday.com", "myworkdayjobs.com", "github.com", "githubusercontent.com",
)


# --- pure --------------------------------------------------------------------------------
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


def is_vendor_host(host: str | None) -> bool:
    h = (host or "").lower()
    return any(h == s or h.endswith("." + s) for s in VENDOR_HOST_SUFFIXES)


def own_domain_from_url(url: str | None) -> str | None:
    """The employer's own domain if `url` is on it, else None (a vendor-hosted board)."""
    host = urlparse(url or "").hostname
    if not host or is_vendor_host(host):
        return None
    return normalise_domain(host)


def sender_matches(sender_domain: str | None, domain: str) -> tuple[bool, str]:
    s = normalise_domain(sender_domain)
    if not s:
        return False, "没有发件域名"
    if s == domain or s.endswith("." + domain):
        return True, f"发件域名 {s} 属于 {domain}"
    return False, f"发件域名 {s} 不是 {domain}；相似域名是冒充的常用手法，按不通过处理"


def red_flags_in(*texts) -> list[str]:
    blob = " ".join(str(t or "") for t in texts).lower()
    return [w for w in RED_FLAGS if w.lower() in blob]


def email_on_domain(email: str, domain: str) -> bool:
    host = email.rsplit("@", 1)[-1].strip().lower()
    domain = domain.lower()
    return bool(host) and (host == domain or host.endswith("." + domain))


# --- one plain GET each --------------------------------------------------------------------
def _get(url: str, timeout: float | None = None) -> httpx.Response | None:
    try:
        return httpx.get(
            url, timeout=timeout or config.HTTP_TIMEOUT_SECONDS, follow_redirects=True,
            headers={"User-Agent": config.USER_AGENT},
        )
    except httpx.HTTPError:
        return None


def homepage_check(domain: str, icp: str | None = None, name: str | None = None) -> dict:
    """What the employer's own homepage says: its ICP 备案号 and whether the name appears."""
    r = _get(f"https://{domain}/")
    if r is None:
        return {"status": "unavailable", "reason": "network", "icp_on_page": [],
                "note": f"本次没有连上 https://{domain}/（网络不通或超时），说明的是这次查询的网络，不是这个站"}
    if r.status_code != 200:
        return {"status": "unavailable", "reason": "http_status", "icp_on_page": [],
                "note": f"https://{domain}/ 回了 HTTP {r.status_code}，首页读不到"}
    html = r.text
    found = sorted({re.sub(r"\s+", "", f) for f in ICP_RE.findall(html)})
    out = {"icp_on_page": found, "name_on_page": bool(name and name in html)}
    want = re.sub(r"\s+", "", icp or "")
    if want:
        out["icp_matches"] = want in found
        out["status"] = "verified" if out["icp_matches"] else "not_verified"
        out["note"] = ("首页页脚有申请人给的备案号" if out["icp_matches"]
                       else f"首页没有申请人给的备案号 {want}；页脚备案号 {found or '无'}")
    else:
        out["status"] = "verified" if found else "not_verified"
        out["note"] = ("首页页脚有备案号 " + ", ".join(found)) if found else "首页没有备案号（海外公司正常；国内公司值得问一句）"
    if name and not out["name_on_page"]:
        out["note"] += "；首页正文没有出现这个名字（只写简称的站很常见）"
    return out


def domain_age(domain: str) -> dict:
    """Registration date via RDAP (rdap.org bootstraps to the right registry)."""
    r = _get(f"https://rdap.org/domain/{domain}")
    if r is None:
        # A network failure is about this query, not about the domain: say so, or a seeker
        # behind a restricted network reads "no record" as a mark against the employer.
        return {"status": "unavailable", "reason": "network",
                "note": "本次没有连上 RDAP（网络不通或超时），说明的是这次查询的网络，不是这个域名"}
    if r.status_code != 200:
        return {"status": "unavailable", "reason": "no_record",
                "note": f"RDAP 没有这个域名的注册记录（HTTP {r.status_code}；.cn 域名常见）"}
    try:
        events = r.json().get("events", [])
        reg = next((e["eventDate"] for e in events if e.get("eventAction") == "registration"), None)
    except (ValueError, KeyError, TypeError, AttributeError):
        reg = None
    if not reg:
        return {"status": "unavailable", "note": "RDAP 返回里没有注册日期"}
    registered = dt.datetime.fromisoformat(reg.replace("Z", "+00:00")).date()
    age = (dt.date.today() - registered).days
    return {"status": "verified" if age >= MIN_DOMAIN_AGE_DAYS else "not_verified",
            "registered": registered.isoformat(), "age_days": age,
            "note": f"域名注册于 {registered}，{age} 天" + ("" if age >= MIN_DOMAIN_AGE_DAYS else f"，不足 {MIN_DOMAIN_AGE_DAYS} 天")}


def wayback_first_capture(domain: str) -> dict:
    """Earliest Wayback Machine capture that answered 200."""
    r = _get(f"https://web.archive.org/cdx/search/cdx?url={domain}&output=json&limit=1&fl=timestamp&filter=statuscode:200")
    if r is None:
        return {"status": "unavailable", "reason": "network",
                "note": "本次没有连上互联网档案馆（网络不通或超时），说明的是这次查询的网络，不是这个站"}
    if r.status_code != 200:
        return {"status": "unavailable", "reason": "http_status", "note": f"互联网档案馆回了 HTTP {r.status_code}，没有给出记录"}
    try:
        rows = r.json()
        ts = rows[1][0] if len(rows) > 1 else None
    except (ValueError, IndexError, TypeError):
        ts = None
    if not ts:
        return {"status": "unavailable", "note": "互联网档案馆没有这个站的抓取记录（新站或被 robots 挡住）"}
    first = dt.datetime.strptime(ts[:8], "%Y%m%d").date()
    age = (dt.date.today() - first).days
    return {"status": "verified" if age >= MIN_DOMAIN_AGE_DAYS else "not_verified",
            "first_capture": first.isoformat(), "age_days": age,
            "note": f"互联网档案馆首次抓取 {first}，{age} 天前"}


def phone_on_page(phone: str | None, page: str | None, domain: str) -> dict:
    if not phone or not page:
        return {"status": "not_verified", "note": "没有公开电话或它所在的页面网址"}
    if not same_domain(urlparse(page).hostname, domain):
        return {"status": "not_verified", "note": f"电话所在页面 {page} 不在 {domain} 域名下；回拨号码必须来自公司自己的站"}
    r = _get(page)
    if r is None or r.status_code != 200:
        return {"status": "unavailable", "note": "电话页面打不开，人工到官网找号码"}
    digits = re.sub(r"\D", "", phone)
    ok = len(digits) >= 7 and digits in re.sub(r"\D", "", r.text)
    return {"status": "verified" if ok else "not_verified",
            "note": "号码出现在公司自己的页面上，回拨它" if ok else "页面上没有这个号码；回拨时用页面上的号码，不用邮件里的"}


def footprints(links: list[str | None], domain: str) -> dict:
    checked = []
    for u in [x for x in links if x]:
        r = _get(u)
        checked.append({"url": u, "ok": bool(r is not None and r.status_code == 200),
                        "own_domain": same_domain(urlparse(u).hostname, domain)})
    if not checked:
        return {"status": "not_verified", "note": "没有行业足迹链接", "links": []}
    resolving = [c for c in checked if c["ok"]]
    if resolving and any(c["own_domain"] for c in resolving):
        status = "verified"
    elif resolving:
        status = "not_verified"
    else:
        status = "unavailable"
    return {"status": status, "links": checked,
            "note": "链接可打开；是不是智驾 / 具身 / AI 基础设施的真足迹，要人工看" if resolving else "链接都打不开"}
