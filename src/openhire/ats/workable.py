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
        # The widget lists a job once per city it is open in, same shortcode each time (live
        # 2026-10-12: Flexion's Zürich + San Francisco roles came back as two entries, Agile
        # Robots' Palo Alto + Petaluma technician likewise). One job is one row here, carrying
        # every city it names, so the index keeps one primary key per job and count_on_board
        # counts jobs, not job-city pairs.
        grouped: dict[str, tuple[dict, list[str]]] = {}
        for j in payload["jobs"]:
            ats_job_id = str(j.get("shortcode") or j.get("id") or "").strip()
            if not ats_job_id:
                continue
            if ats_job_id in grouped:
                locs = grouped[ats_job_id][1]
                locs.extend(loc for loc in self._locations(j) if loc not in locs)
                continue
            grouped[ats_job_id] = (j, self._locations(j))
        records: list[JobRecord] = []
        for ats_job_id, (j, locs) in grouped.items():
            parts = [j.get("description"), j.get("requirements"), j.get("benefits")]
            desc = "\n\n".join(p for p in parts if isinstance(p, str) and p.strip())
            vendor_url = j.get("application_url") or j.get("url")
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=(j.get("title") or "").strip(),
                    description_raw=html_to_text(desc),
                    apply_channel=self.resolve_apply(tenant, ats_job_id, vendor_url),
                    location="; ".join(locs) or None,
                    remote_hint=self._remote_hint(j),
                    posted_at=_date_to_dt(j.get("published_on") or j.get("published") or j.get("created_at")),
                    # The widget carries no last-touched field.
                    updated_at=None,
                )
            )
        return records

    @staticmethod
    def _locations(j) -> list[str]:
        """Every city the entry names, each as "city, region, country"; de-duplicated, in order."""
        locs = j.get("locations")
        entries = [loc for loc in locs if isinstance(loc, dict)] if isinstance(locs, list) else []
        if not entries:
            entries = [{"city": j.get("city"), "region": j.get("state"), "country": j.get("country")}]
        out: list[str] = []
        for e in entries:
            parts = [e.get("city"), e.get("region") or e.get("state"), e.get("country")]
            text = ", ".join(str(x).strip() for x in parts if x and str(x).strip())
            if text and text not in out:
                out.append(text)
        return out

    @staticmethod
    def _remote_hint(j) -> str:
        if j.get("telecommuting") is True or j.get("remote") is True:
            return "remote"
        wt = str(j.get("workplace") or j.get("workplace_type") or "").lower().replace("_", "").replace("-", "").replace(" ", "")
        if wt in ("remote", "hybrid"):
            return wt
        if wt in ("onsite", "on site"):
            return "onsite"
        loc = "; ".join(WorkableClient._locations(j)).lower()
        if "remote" in loc:
            return "remote"
        return "unknown"
