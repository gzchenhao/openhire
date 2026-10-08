"""Employer self-reported rosters: the door for employers whose own system we cannot read.

Everything else in this package reads an employer's public ATS or first-party mirror. A
survey of 28 small employers in our target industry (reports/060, 2026-10-08) found the
Chinese ones on Feishu Recruitment (request-signed, never bypassed), on the BOSS直聘
platform only, or on a careers page with no job list, and none with machine-readable
postings. Those employers cannot be indexed, so they cannot claim either. This adapter is
the smallest honest way in, and it exists under four conditions that keep it from turning
this index into a job board:

  1. Only an employer whose corporate identity was verified (a roster sent from the
     corporate domain, the same proof a claim needs, never payment) gets an entry.
  2. Every row says what it is: `source` is `employer_self_reported`, and the posting
     date carries `date_signal: self_reported`, because the employer typed it. An ATS
     date is system-written and cannot be edited; this one can, and the row says so.
  3. A row expires MAX_AGE_DAYS after the later of its posting date and its renewal
     date. Keeping a posting alive takes the employer sending the sheet again; nothing
     here is kept alive by inertia.
  4. Nothing about ranking or ghost_score changes. The same locked pure functions
     apply, and nothing here costs the employer anything.

The roster is a JSON file in this repository (`employers/<slug>.json`), written by the
maintainer from the employer's spreadsheet (`scripts/import_employer_roster.py`) after
verification. The adapter fetches it over HTTPS like any other source, so the weekly
snapshot workflow and a user's `refresh_index` both read the same file. The employer's
registration (name, corporate domain, careers page, verification date) is declared in
SELF_REPORTED_EMPLOYERS below, in code, so that `careers_url` and the apply-link trust
check need no network and an entry is a reviewable diff.

An apply link is handed to a seeker only when it is https on the employer's own domain;
anything else falls back to the employer's careers page, which we verified ourselves.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .base import ATSClient, JobRecord

VENDOR = "self_reported"
SOURCE = "employer_self_reported"   # protocol field ② for every row from this adapter
MAX_AGE_DAYS = 90                   # a self-reported posting lives this long per renewal
_RAW = "https://raw.githubusercontent.com/gzchenhao/openhire/main/employers"


@dataclass(frozen=True)
class SelfReportedEmployer:
    slug: str          # companies.id, same convention as every other vendor
    name: str          # bilingual display name
    domain: str        # the corporate domain the roster was sent from (identity proof)
    careers_url: str   # the employer's own page a seeker can always be sent to
    verified_on: str   # ISO date the corporate identity was verified


# Declarative. An employer enters here only after the maintainer verified the corporate
# identity behind the roster; the matching `employers/<slug>.json` is committed alongside.
SELF_REPORTED_EMPLOYERS: dict[str, SelfReportedEmployer] = {
    # none yet (2026-10-08); the path is described at docs/employers.html
}


def trusted_hosts(slug: str) -> set[str]:
    """Hosts an apply link may be on for this employer: its own domain and subdomains
    are matched by `apply_url_is_trusted`; this returns the bare domain."""
    emp = SELF_REPORTED_EMPLOYERS.get(slug)
    return {emp.domain.lower()} if emp else set()


def _date(value) -> dt.datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        d = dt.date.fromisoformat(value[:10])
    except ValueError:
        return None
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


def _int(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _on_domain(url: str | None, domain: str | None) -> bool:
    if not url or not domain:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    domain = domain.lower()
    return parsed.scheme == "https" and (host == domain or host.endswith("." + domain))


class SelfReportedClient(ATSClient):
    vendor = VENDOR

    def endpoint(self, tenant: str) -> str:
        return f"{_RAW}/{tenant}.json"

    def careers_url(self, tenant: str) -> str:
        emp = SELF_REPORTED_EMPLOYERS.get(tenant)
        return emp.careers_url if emp else self.endpoint(tenant)

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("postings"), list)

    def parse(self, payload, tenant: str, now: dt.datetime | None = None) -> list[JobRecord]:
        now = now or dt.datetime.now(dt.timezone.utc)
        emp = SELF_REPORTED_EMPLOYERS.get(tenant)
        domain = emp.domain if emp else None
        fallback = emp.careers_url if emp else None
        out: list[JobRecord] = []
        for p in payload.get("postings", []):
            if not isinstance(p, dict):
                continue
            title = re.sub(r"\s+", " ", str(p.get("title") or "")).strip()
            posted = _date(p.get("posted_at"))
            renewed = _date(p.get("renewed_at"))
            if not title or posted is None:
                # A self-reported row without a title or a date is not a posting we can
                # describe honestly, so it is not one we index.
                continue
            anchor = max(posted, renewed) if renewed else posted
            if (now - anchor).days > MAX_AGE_DAYS:
                continue  # expired; the employer renews by sending the sheet again
            apply_url = p.get("apply_url")
            apply_channel = apply_url if _on_domain(apply_url, domain) else fallback
            if not apply_channel:
                continue
            description = str(p.get("description") or "").strip()
            email = str(p.get("apply_email") or "").strip()
            if email:
                # A company mailbox the employer chose to publish, not a person's.
                description = (description + f"\n\n投递邮箱：{email}").strip()
            location = str(p.get("location") or "").strip() or None
            job_id = str(p.get("id") or "").strip() or hashlib.sha1(
                f"{tenant}|{title}|{location or ''}|{posted.date().isoformat()}".encode("utf-8")
            ).hexdigest()[:12]
            out.append(JobRecord(
                ats_job_id=job_id,
                title=title,
                description_raw=description,
                apply_channel=apply_channel,
                location=location,
                salary_min=_int(p.get("salary_min")),
                salary_max=_int(p.get("salary_max")),
                salary_currency=(p.get("salary_currency") or None),
                salary_period=(p.get("salary_period") or "monthly"),
                posted_at=posted,
                updated_at=renewed,
            ))
        return out
