"""ATS client abstractions and a normalized job record.

All three vendors (Greenhouse, Lever, Ashby) are read through their *public,
unauthenticated* job-board endpoints. Each client turns a vendor payload into a list
of `JobRecord`s with a stable shape, so the pipeline is vendor-agnostic downstream.

`source` for every record is `ats_public_api` — protocol field ②.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTINL_RE = re.compile(r"\n{3,}")


# --- apply_channel resolution (protocol field ⑤) ------------------------------
# "点开就能投" is a product promise: every apply_channel MUST deep-link to the
# specific job's application. Many employers embed their ATS on their own domain
# (e.g. coreweave.com/careers/job?...&gh_jid=123) and those embeds often render a
# generic listing instead of the job — so we only trust a vendor-provided URL when it
# is on a canonical ATS host AND carries the job id in its path. Otherwise we fall back
# to a deterministically-built canonical ATS apply URL that is guaranteed to deep-link.
#
# These canonical hosts are still first-party (the employer's own ATS tenant), so this
# respects the protocol rule that apply_channel is always the employer's own endpoint.
ATS_APPLY_HOSTS: dict[str, set[str]] = {
    "greenhouse": {"boards.greenhouse.io", "job-boards.greenhouse.io"},
    "lever": {"jobs.lever.co"},
    "ashby": {"jobs.ashbyhq.com"},
}


@dataclass
class ApplyResolution:
    url: str
    used_fallback: bool  # True when we replaced the vendor URL with a canonical one
    is_embed: bool       # True when the vendor URL was an employer self-hosted embed


def canonical_apply_url(vendor: str, tenant: str, ats_job_id: str) -> str:
    """A deterministic, deep-linking application URL on the employer's ATS tenant.

    Greenhouse uses the hosted application form (`/embed/job_app`) rather than the job
    page, because some tenants configure their hosted job page to redirect back to a
    (broken) employer embed — the application form is never hijacked that way.
    """
    if vendor == "greenhouse":
        return f"https://boards.greenhouse.io/embed/job_app?for={tenant}&token={ats_job_id}"
    if vendor == "lever":
        return f"https://jobs.lever.co/{tenant}/{ats_job_id}"
    if vendor == "ashby":
        return f"https://jobs.ashbyhq.com/{tenant}/{ats_job_id}"
    raise ValueError(f"unknown vendor: {vendor!r}")


def resolve_apply_channel(
    vendor: str, tenant: str, ats_job_id: str, vendor_url: str | None
) -> ApplyResolution:
    """Choose a guaranteed-deep-linking apply_channel (see module note above)."""
    hosts = ATS_APPLY_HOSTS.get(vendor, set())
    canonical = canonical_apply_url(vendor, tenant, ats_job_id)

    if vendor_url:
        parsed = urlparse(vendor_url)
        host = (parsed.netloc or "").lower()
        # Trust only a canonical ATS host that carries the job id in the path.
        if host in hosts and ats_job_id in (parsed.path or ""):
            return ApplyResolution(url=vendor_url, used_fallback=False, is_embed=False)
        # A non-ATS host = an employer self-hosted embed; treat as unreliable.
        is_embed = bool(host) and host not in hosts
        return ApplyResolution(url=canonical, used_fallback=True, is_embed=is_embed)

    return ApplyResolution(url=canonical, used_fallback=True, is_embed=False)


def html_to_text(raw: str | None) -> str:
    """Best-effort HTML → readable plain text (also used for content hashing).

    Greenhouse returns entity-encoded HTML (``&lt;div&gt;``) while Ashby returns real
    HTML, so we unescape *first*, then translate block tags, then strip remaining tags.
    """
    if not raw:
        return ""
    text = html.unescape(raw)
    text = text.replace("</p>", "\n\n").replace("<br>", "\n").replace("<br/>", "\n")
    text = text.replace("<br />", "\n").replace("</li>", "\n").replace("<li>", "• ")
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)  # second pass for doubly-encoded entities
    text = _WS_RE.sub(" ", text)
    text = _MULTINL_RE.sub("\n\n", text)
    return text.strip()


@dataclass
class JobRecord:
    """Vendor-neutral job as pulled from a public ATS endpoint."""

    ats_job_id: str
    title: str
    description_raw: str
    apply_channel: str  # protocol field ⑤ — always the employer's own apply URL
    location: str | None = None
    remote_hint: str | None = None  # remote|hybrid|onsite|unknown from ATS-native fields
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    posted_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None


@dataclass
class FetchResult:
    """Outcome of hitting one tenant. `ok` gates whether the tenant is valid."""

    ok: bool
    status: int
    records: list[JobRecord] = field(default_factory=list)
    error: str | None = None

    @property
    def count(self) -> int:
        return len(self.records)


class ATSClient(ABC):
    vendor: str = ""

    @abstractmethod
    def endpoint(self, tenant: str) -> str:
        """Public API URL for a tenant."""

    @abstractmethod
    def careers_url(self, tenant: str) -> str:
        """Human-facing job board URL for a tenant."""

    @abstractmethod
    def parse(self, payload, tenant: str) -> list[JobRecord]:
        """Turn a decoded JSON payload into JobRecords for a given tenant."""

    def resolve_apply(self, tenant: str, ats_job_id: str, vendor_url: str | None) -> str:
        """Resolve a guaranteed-deep-linking apply_channel for a job."""
        return resolve_apply_channel(self.vendor, tenant, ats_job_id, vendor_url).url

    async def fetch(self, client: httpx.AsyncClient, tenant: str) -> FetchResult:
        """Fetch + validate a tenant. A tenant is valid only on HTTP 200 with a
        well-formed jobs array (README: 请求 200 且返回 jobs 数组才入库)."""
        url = self.endpoint(tenant)
        try:
            resp = await client.get(url)
        except httpx.HTTPError as exc:
            return FetchResult(ok=False, status=0, error=f"{type(exc).__name__}: {exc}")

        if resp.status_code != 200:
            return FetchResult(ok=False, status=resp.status_code, error="non-200")

        try:
            payload = resp.json()
        except ValueError:
            return FetchResult(ok=False, status=200, error="non-json body")

        if not self._has_jobs_array(payload):
            return FetchResult(ok=False, status=200, error="no jobs array")

        try:
            records = self.parse(payload, tenant)
        except Exception as exc:  # a malformed record set should not kill the crawl
            return FetchResult(ok=False, status=200, error=f"parse error: {exc}")

        return FetchResult(ok=True, status=200, records=records)

    @staticmethod
    @abstractmethod
    def _has_jobs_array(payload) -> bool:
        ...


def _epoch_ms_to_dt(ms) -> dt.datetime | None:
    if not ms:
        return None
    try:
        return dt.datetime.fromtimestamp(int(ms) / 1000, tz=dt.timezone.utc)
    except (ValueError, OSError, TypeError):
        return None


def _iso_to_dt(s) -> dt.datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
