"""Which public job board a URL points at.

`read_board` (reports/069) lets a seeker's assistant read ANY employer's board on a vendor
this index already knows how to read, whether or not the employer is in the index. The
seeker pastes the careers URL; this module turns it into the (vendor, tenant) pair the
adapters take. Nothing here touches the network.

Only vendors with a public, unauthenticated board endpoint can be read. A Feishu Hire
portal (request signatures), SuccessFactors, Taleo, iCIMS and the like are refused
with the reason, never scraped (CLAUDE.md: signatures, captchas and login walls mean stop).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

# Hosts a seeker may paste, each mapped to the vendor and to how the tenant is read off the
# URL. Order matters only for readability.
_GREENHOUSE_HOSTS = {"job-boards.greenhouse.io", "boards.greenhouse.io", "boards-api.greenhouse.io"}
_LEVER_HOSTS = {"jobs.lever.co", "api.lever.co", "jobs.eu.lever.co"}
_ASHBY_HOSTS = {"jobs.ashbyhq.com", "api.ashbyhq.com"}
_MOKA_HOSTS = {"app.mokahr.com"}

# Portals we know and deliberately cannot read, with the reason a seeker should hear.
# One sentence shared by every portal a person can read but this index cannot: an assistant
# that has a browser tool (WorkBuddy, 豆包, Claude with a browser) may open the page and read
# it the way a person does. That is reading, not scraping, and it is the assistant's call.
BROWSER_HINT = "助手有浏览器工具的话，可以直接打开这个门户阅读：现读、不入库、不盯、无发布日期。"

CLOSED_PORTALS = {
    "feishu.cn": "飞书招聘门户的列表接口要请求签名，属于访问控制，这个索引不读（见 reports/014）；只能打开门户自己看，或由雇主在飞书开放平台授权只读。" + BROWSER_HINT,
    "larksuite.com": "Lark Hire 门户的列表接口要请求签名，属于访问控制，这个索引不读；只能打开门户自己看。" + BROWSER_HINT,
    "successfactors.com": "SuccessFactors 没有公开的岗位接口，这个索引不读；打开页面自己看。" + BROWSER_HINT,
    "taleo.net": "Taleo 没有公开的岗位接口，这个索引不读；打开页面自己看。" + BROWSER_HINT,
    "icims.com": "iCIMS 没有公开的岗位接口，这个索引不读；打开页面自己看。" + BROWSER_HINT,
    "linkedin.com": "LinkedIn 禁止自动访问，这个索引不读；在 LinkedIn 上自己看。",
    "jobsdb.com": "JobsDB 是招聘网站不是雇主自己的系统，这个索引只读雇主自己的招聘系统。",
    "zhipin.com": "BOSS 直聘是招聘网站不是雇主自己的系统，这个索引只读雇主自己的招聘系统。",
}

SUPPORTED = "Greenhouse (job-boards.greenhouse.io/<board>)、Lever (jobs.lever.co/<site>)、Ashby (jobs.ashbyhq.com/<board>)、Moka (app.mokahr.com/apply/<org>/<siteId>)、北森 (<tenant>.zhiye.com)、Workable (apply.workable.com/<subdomain>)、SmartRecruiters (jobs.smartrecruiters.com/<company>)、Workday (<account>.wd5.myworkdayjobs.com/<site>)"

_WORKDAY_SUFFIX = ".myworkdayjobs.com"
_WORKDAY_CLUSTER = re.compile(r"^wd\d+$")
_LOCALE = re.compile(r"^[a-z]{2}(-[A-Za-z]{2})?$")   # en-US, zh-CN, fr: path prefixes Workday adds

_WORKABLE_HOSTS = {"apply.workable.com"}
# Workable's own sites on the same domain, never a tenant.
_WORKABLE_NOT_TENANTS = {"www", "apply", "jobs", "help", "resources", "careers", "api", "app"}
_SMARTRECRUITERS_HOSTS = {"jobs.smartrecruiters.com", "careers.smartrecruiters.com", "api.smartrecruiters.com"}

_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class BoardNotSupported(ValueError):
    """The URL is not a board this index knows how to read; `.reason` says why."""

    def __init__(self, reason: str, hint: str):
        super().__init__(hint)
        self.reason = reason
        self.hint = hint


def _first_segment(path: str) -> str | None:
    parts = [p for p in path.split("/") if p]
    return parts[0] if parts else None


def detect_board(url: str) -> tuple[str, str]:
    """(vendor, tenant) for a pasted careers URL, or BoardNotSupported with the reason."""
    raw = (url or "").strip()
    if not raw:
        raise BoardNotSupported("bad_url", "Give the employer's careers URL. Supported: " + SUPPORTED)
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if not host:
        raise BoardNotSupported("bad_url", "That is not a URL. Supported: " + SUPPORTED)

    for closed, why in CLOSED_PORTALS.items():
        if host == closed or host.endswith("." + closed):
            raise BoardNotSupported("closed_portal", why)

    if host in _GREENHOUSE_HOSTS:
        if host == "boards-api.greenhouse.io":
            m = re.match(r"^/v1/boards/([^/]+)", path)
            tenant = m.group(1) if m else None
        elif path.startswith("/embed/job_board") or path.startswith("/embed/job_app"):
            tenant = (parse_qs(parsed.query).get("for") or [None])[0]
        else:
            tenant = _first_segment(path)
        return _checked("greenhouse", tenant, "job-boards.greenhouse.io/<board>")

    if host in _LEVER_HOSTS:
        if host == "api.lever.co":
            m = re.match(r"^/v0/postings/([^/]+)", path)
            tenant = m.group(1) if m else None
        else:
            tenant = _first_segment(path)
        return _checked("lever", tenant, "jobs.lever.co/<site>")

    if host in _ASHBY_HOSTS:
        if host == "api.ashbyhq.com":
            m = re.match(r"^/posting-api/job-board/([^/]+)", path)
            tenant = m.group(1) if m else None
        else:
            tenant = _first_segment(path)
        return _checked("ashby", tenant, "jobs.ashbyhq.com/<board>")

    if host in _MOKA_HOSTS:
        m = re.match(r"^/apply/([^/]+)/(\d+)", path)
        if not m:
            raise BoardNotSupported("bad_url", "A Moka portal URL looks like app.mokahr.com/apply/<org>/<siteId>.")
        return "moka", f"{m.group(1)}/{m.group(2)}"

    if host in _WORKABLE_HOSTS:
        m = re.match(r"^/api/v1/widget/accounts/([^/?]+)", path)
        tenant = m.group(1) if m else _first_segment(path)
        return _checked("workable", tenant, "apply.workable.com/<subdomain>")

    if host.endswith(".workable.com") and host.count(".") == 2:
        tenant = host.split(".", 1)[0]
        if tenant in _WORKABLE_NOT_TENANTS:
            raise BoardNotSupported("bad_url", "A Workable board URL looks like apply.workable.com/<subdomain>.")
        return _checked("workable", tenant, "apply.workable.com/<subdomain>")

    if host in _SMARTRECRUITERS_HOSTS:
        if host == "api.smartrecruiters.com":
            m = re.match(r"^/v1/companies/([^/]+)", path)
            tenant = m.group(1) if m else None
        else:
            tenant = _first_segment(path)
        return _checked("smartrecruiters", tenant, "jobs.smartrecruiters.com/<company>")

    if host.endswith(_WORKDAY_SUFFIX):
        # <account>.<wdN>.myworkdayjobs.com/<locale?>/<site>/... ; the tenant this index keys
        # on is "<account>.<wdN>/<site>" because the account alone does not name a board
        # (one account can publish several sites) and the cluster is part of the host.
        sub = host[: -len(_WORKDAY_SUFFIX)]
        parts = sub.split(".")
        shape = "A Workday careers URL looks like <account>.wd5.myworkdayjobs.com/<site> (the site name is the first path segment after an optional locale such as en-US)."
        if len(parts) != 2 or not parts[0] or not _WORKDAY_CLUSTER.match(parts[1]):
            raise BoardNotSupported("bad_url", shape)
        segs = [s for s in path.split("/") if s]
        if segs and segs[0] == "wday":
            # the data endpoint itself: /wday/cxs/<account>/<site>/jobs
            segs = segs[3:4] if len(segs) >= 4 and segs[1] == "cxs" else []
        else:
            segs = [s for s in segs if not _LOCALE.match(s)]
        site = segs[0] if segs else None
        if not site or not _SLUG.match(site) or site.lower() in ("job", "jobs", "details", "login"):
            raise BoardNotSupported("bad_url", shape)
        return "workday", f"{sub}/{site}"

    if host.endswith(".zhiye.com") and host.count(".") == 2:
        tenant = host.split(".", 1)[0]
        if tenant in ("www", "app", "api"):
            raise BoardNotSupported("bad_url", "A 北森 portal URL looks like <tenant>.zhiye.com/social/jobs.")
        return "beisen", tenant

    raise BoardNotSupported(
        "unsupported_host",
        f"{host} is not a board this index can read. Supported: {SUPPORTED}. "
        "An employer's own careers page usually links to one of these; otherwise open the page yourself.",
    )


def _checked(vendor: str, tenant: str | None, shape: str) -> tuple[str, str]:
    if not tenant or not _SLUG.match(tenant):
        raise BoardNotSupported("bad_url", f"A {vendor.title()} board URL looks like {shape}.")
    return vendor, tenant
