"""ATS client registry."""

from __future__ import annotations

from .ashby import AshbyClient
from .beisen import BeisenClient
from .base import (
    ATSClient,
    ApplyResolution,
    FetchResult,
    JobRecord,
    canonical_apply_url,
    html_to_text,
    apply_url_is_trusted,
    base_tenant,
    place_matches,
    resolve_apply_channel,
    split_scope,
)
from .comeet import ComeetClient
from .greenhouse import GreenhouseClient
from .lever import LeverClient
from .lixiang import LixiangClient
from .moka import MokaClient
from .personio import PersonioClient
from .rippling import RipplingClient
from .nio import NioClient
from .self_reported import SelfReportedClient
from .smartrecruiters import SmartRecruitersClient
from .workable import WorkableClient
from .workday import WorkdayClient

_CLIENTS: dict[str, ATSClient] = {
    "greenhouse": GreenhouseClient(),
    "lever": LeverClient(),
    "ashby": AshbyClient(),
    "beisen": BeisenClient(),
    "moka": MokaClient(),
    "workable": WorkableClient(),
    "smartrecruiters": SmartRecruitersClient(),
    "workday": WorkdayClient(),
    "rippling": RipplingClient(),
    "personio": PersonioClient(),
    "comeet": ComeetClient(),
    "lixiang": LixiangClient(),  # first-party employer mirror (理想汽车), one tenant
    "nio": NioClient(),
    # Employer self-reported rosters, verified by corporate identity (ats/self_reported.py).
    "self_reported": SelfReportedClient(),
}


async def fetch_scoped(client_impl: ATSClient, http, tenant: str) -> FetchResult:
    """Fetch one board, honouring a seed row's place scope ("<tenant>|place=hong kong"): the
    vendor sees only the tenant before the bar, and only postings in that place come back.
    Workday filters before it reads each posting's details, so Citi's 2,000 worldwide postings
    cost one list read, not 2,000 detail reads (reports/151)."""
    base, place = split_scope(tenant)
    if place is None:
        return await client_impl.fetch(http, tenant)
    if isinstance(client_impl, WorkdayClient):
        res = await client_impl.fetch(http, base, place=place)
    else:
        res = await client_impl.fetch(http, base)
    if res.ok:
        res.records = [r for r in res.records if place_matches(place, r.location)]
    return res


def get_client(vendor: str) -> ATSClient:
    try:
        return _CLIENTS[vendor]
    except KeyError:
        raise ValueError(f"unknown ATS vendor: {vendor!r}") from None


def all_vendors() -> list[str]:
    return list(_CLIENTS)


__all__ = [
    "ATSClient",
    "ApplyResolution",
    "AshbyClient",
    "BeisenClient",
    "FetchResult",
    "GreenhouseClient",
    "JobRecord",
    "LeverClient",
    "LixiangClient",
    "MokaClient",
    "NioClient",
    "SelfReportedClient",
    "SmartRecruitersClient",
    "WorkableClient",
    "canonical_apply_url",
    "get_client",
    "all_vendors",
    "html_to_text",
    "apply_url_is_trusted",
    "resolve_apply_channel",
]
