"""Workable public widget API (no key, one call per tenant).

GET https://apply.workable.com/api/v1/widget/accounts/{subdomain}?details=true

Workable documents this as the "Widget API": the JSON behind the careers list an employer
embeds on its own site. `details=true` adds the description / requirements / benefits HTML
per job. There is no pagination and no salary field. `published_on` is a bare date, so the
posting date is stored as that day at 00:00 UTC.

Written from the vendor's documentation (reports/075): the cloud session that wrote it
cannot reach apply.workable.com, so the first live read ran on the maintainer's machine
through the local task queue. Anything the live payload disagrees with gets fixed there.
"""

from __future__ import annotations

import datetime as dt

from .base import ATSClient, JobRecord, _iso_to_dt, html_to_text


def _date_to_dt(s) -> dt.datetime | None:
    """A bare `YYYY-MM-DD` (what the widget reports) as an aware UTC midnight, so it
    compares with every other vendor's timestamps; a full ISO timestamp passes through."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if len(s) == 10:
        try:
            d = dt.date.fromisoformat(s)
        except ValueError:
            return None
        return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)
    parsed = _iso_to_dt(s)
    if parsed is not None and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


class WorkableClient(ATSClient):
    vendor = "workable"

    def endpoint(self, tenant: str) -> str:
        return f"https://apply.workable.com/api/v1/widget/accounts/{tenant}?details=true"

    def careers_url(self, tenant: str) -> str:
        return f"https://apply.workable.com/{tenant}/"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("jobs"), list)

    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for j in payload["jobs"]:
            ats_job_id = str(j.get("shortcode") or j.get("id") or "").strip()
            if not ats_job_id:
                continue
            parts = [j.get("description"), j.get("requirements"), j.get("benefits")]
            desc = "\n\n".join(p for p in parts if isinstance(p, str) and p.strip())
            vendor_url = j.get("application_url") or j.get("url")
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=(j.get("title") or "").strip(),
                    description_raw=html_to_text(desc),
                    apply_channel=self.resolve_apply(tenant, ats_job_id, vendor_url),
                    location=self._location(j),
                    remote_hint=self._remote_hint(j),
                    posted_at=_date_to_dt(j.get("published_on") or j.get("published") or j.get("created_at")),
                    # The widget carries no last-touched field.
                    updated_at=None,
                )
            )
        return records

    @staticmethod
    def _location(j) -> str | None:
        locs = j.get("locations")
        if isinstance(locs, list) and locs and isinstance(locs[0], dict):
            first = locs[0]
            parts = [first.get("city"), first.get("region") or first.get("state"), first.get("country")]
        else:
            parts = [j.get("city"), j.get("state"), j.get("country")]
        text = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
        return text or None

    @staticmethod
    def _remote_hint(j) -> str:
        if j.get("telecommuting") is True or j.get("remote") is True:
            return "remote"
        wt = str(j.get("workplace") or j.get("workplace_type") or "").lower().replace("_", "")
        if wt in ("remote", "hybrid"):
            return wt
        if wt in ("onsite", "on site"):
            return "onsite"
        loc = str(WorkableClient._location(j) or "").lower()
        if "remote" in loc:
            return "remote"
        return "unknown"
