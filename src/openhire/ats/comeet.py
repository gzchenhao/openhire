"""Comeet public careers API (one call per tenant).

GET https://www.comeet.co/careers-api/2.0/company/{uid}/positions?token={token}&details=true

Comeet's careers API needs the company uid and a careers token. Neither is in the board
URL; the employer publishes both in its own careers page (the Comeet WordPress plugin
writes them into an inline `comeetvar`), as plain text in the page itself, for this
public read. So this index keys a Comeet board as "<slug>/<uid>/<token>", read off that
page by a maintainer, and `read_board` cannot derive one from a pasted URL.

A top-level array of positions: `{uid, name, location: {name, is_remote}, time_updated,
url_comeet_hosted_page, url_active_page, details: [{name, value}]}`. `time_updated` is
when the employer last changed the posting, not when it was posted, so it is stored as
updated_at and the row is `date_signal: not_reported_by_ats`.

Endpoint and field names follow career-ops' Comeet provider (MIT,
https://github.com/career-ops-hq/career-ops, providers/comeet.mjs); reports/122. A plain
GET with our own User-Agent.
"""

from __future__ import annotations

from .base import ATSClient, JobRecord, _iso_to_dt, html_to_text

API_HOST = "www.comeet.co"
BOARD_HOST = "www.comeet.com"


# Comeet's own workplace_type, as its hosted page shows it (On-site / Hybrid / Remote).
_WORKPLACE = {"on-site": "onsite", "onsite": "onsite", "hybrid": "hybrid", "remote": "remote"}


def split_tenant(tenant: str) -> tuple[str, str, str]:
    """`imagry/B7.00F/<token>` -> ("imagry", "B7.00F", "<token>")."""
    slug, uid, token = tenant.split("/", 2)
    return slug, uid, token


class ComeetClient(ATSClient):
    vendor = "comeet"

    def endpoint(self, tenant: str) -> str:
        _, uid, token = split_tenant(tenant)
        return f"https://{API_HOST}/careers-api/2.0/company/{uid}/positions?token={token}&details=true"

    def careers_url(self, tenant: str) -> str:
        slug, uid, _ = split_tenant(tenant)
        return f"https://{BOARD_HOST}/jobs/{slug}/{uid}"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, list)

    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for j in payload:
            if not isinstance(j, dict):
                continue
            ats_job_id = str(j.get("uid") or "").strip()
            title = (j.get("name") or "").strip()
            if not ats_job_id or not title:
                continue
            loc = j.get("location") if isinstance(j.get("location"), dict) else {}
            location = (loc.get("name") or "").strip() or None
            if loc.get("is_remote"):
                remote = "remote"
                if not location or "remote" not in location.lower():
                    location = f"{location}, Remote" if location else "Remote"
            else:
                remote = _WORKPLACE.get(str(j.get("workplace_type") or "").lower().replace("_", "-").replace(" ", "-"), "unknown")
            parts = []
            for d in j.get("details") or []:
                if isinstance(d, dict) and (d.get("value") or "").strip():
                    name = (d.get("name") or "").strip()
                    parts.append(f"{name}\n{d['value']}" if name else d["value"])
            records.append(JobRecord(
                ats_job_id=ats_job_id,
                title=title,
                description_raw=html_to_text("\n\n".join(parts)),
                apply_channel=self.resolve_apply(tenant, ats_job_id, j.get("url_comeet_hosted_page")),
                location=location,
                remote_hint=remote,
                posted_at=None,
                updated_at=_iso_to_dt((j.get("time_updated") or "").strip()),
            ))
        return records
