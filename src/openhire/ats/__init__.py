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
    resolve_apply_channel,
)
from .greenhouse import GreenhouseClient
from .lever import LeverClient
from .lixiang import LixiangClient
from .moka import MokaClient

_CLIENTS: dict[str, ATSClient] = {
    "greenhouse": GreenhouseClient(),
    "lever": LeverClient(),
    "ashby": AshbyClient(),
    "beisen": BeisenClient(),
    "moka": MokaClient(),
    "lixiang": LixiangClient(),  # first-party employer mirror (理想汽车), one tenant
}


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
    "canonical_apply_url",
    "get_client",
    "all_vendors",
    "html_to_text",
    "apply_url_is_trusted",
    "resolve_apply_channel",
]
