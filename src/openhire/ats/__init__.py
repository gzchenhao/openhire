"""ATS client registry."""

from __future__ import annotations

from .ashby import AshbyClient
from .base import (
    ATSClient,
    ApplyResolution,
    FetchResult,
    JobRecord,
    canonical_apply_url,
    html_to_text,
    resolve_apply_channel,
)
from .greenhouse import GreenhouseClient
from .lever import LeverClient

_CLIENTS: dict[str, ATSClient] = {
    "greenhouse": GreenhouseClient(),
    "lever": LeverClient(),
    "ashby": AshbyClient(),
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
    "FetchResult",
    "GreenhouseClient",
    "JobRecord",
    "LeverClient",
    "canonical_apply_url",
    "get_client",
    "all_vendors",
    "html_to_text",
    "resolve_apply_channel",
]
