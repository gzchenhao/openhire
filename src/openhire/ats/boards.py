"""Which public job board a URL points at.

`read_board` (reports/069) lets a seeker's assistant read ANY employer's board on a vendor
this index already knows how to read, whether or not the employer is in the index. The
seeker pastes the careers URL; this module turns it into the (vendor, tenant) pair the
adapters take. Nothing here touches the network.

Only vendors with a public, unauthenticated board endpoint can be read. A Feishu Hire
portal (request signatures), Workday, SuccessFactors, Taleo, iCIMS and the like are refused
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
CLOSED_PORTALS = {
    "feishu.cn": "飞书招聘门户的列表接口要请求签名，属于访问控制，这个索引不读（见 reports/014）；只能打开门户自己看，或由雇主在飞书开放平台授权只读。",
    "larksuite.com": "Lark Hire 门户的列表接口要请求签名，属于访问控制，这个索引不读；只能打开门户自己看。",
    "myworkdayjobs.com": "Workday 没有公开的岗位接口，这个索引不读；打开页面自己看。",
    "successfactors.com": "SuccessFactors 没有公开的岗位接口，这个索引不读；打开页面自己看。",
    "taleo.net": "Taleo 没有公开的岗位接口，这个索引不读；打开页面自己看。",
    "icims.com": "iCIMS 没有公开的岗位接口，这个索引不读；打开页面自己看。",
    "linkedin.com": "LinkedIn 禁止自动访问，这个索引不读；在 LinkedIn 上自己看。",
    "jobsdb.com": "JobsDB 是招聘网站不是雇主自己的系统，这个索引只读雇主自己的招聘系统。",
    "zhipin.com": "BOSS 直聘是招聘网站不是雇主自己的系统，这个索引只读雇主自己的招聘系统。",
}

SUPPORTED = "Greenhouse (job-boards.greenhouse.io/<board>)、Lever (jobs.lever.co/<site>)、Ashby (jobs.ashbyhq.com/<board>)、Moka (app.mokahr.com/apply/<org>/<siteId>)、北森 (<tenant>.zhiye.com)"

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
