"""SQLAlchemy models — a 1:1 mirror of schema.sql.

Table/column names match the canonical Postgres DDL exactly; the privacy tests
introspect these classes to prove `watches` and `applications` carry no PII.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .types import JSONDict, StringArray, TZDateTime


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # slug
    name: Mapped[str] = mapped_column(Text, nullable=False)
    ats_vendor: Mapped[str] = mapped_column(Text, nullable=False)  # greenhouse|lever|ashby
    ats_tenant: Mapped[str] = mapped_column(Text, nullable=False)
    careers_url: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # reserved for v0.3
    last_crawled_at: Mapped[dt.datetime | None] = mapped_column(TZDateTime)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # {company_id}:{ats_job_id}
    company_id: Mapped[str] = mapped_column(Text, ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description_raw: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(StringArray, default=list)
    # Coarse job family (sales|engineering|data|product|design|marketing|ops|other).
    # Populated by a DeepSeek pass (pending); null until then. The filter is a no-op while null.
    role_family: Mapped[str | None] = mapped_column(Text)
    remote_policy: Mapped[str | None] = mapped_column(Text)  # remote|hybrid|onsite|unknown
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(Text)
    salary_inferred: Mapped[bool] = mapped_column(Boolean, default=False)
    location: Mapped[str | None] = mapped_column(Text)
    # Real ATS-provided posting dates — the employer's own truth, distinct from when WE
    # first crawled it (first_seen_at). datePosted and ghost_score age are anchored here;
    # null only when the ATS exposes no date (then we fall back to first_seen_at).
    posted_at: Mapped[dt.datetime | None] = mapped_column(TZDateTime)
    updated_at: Mapped[dt.datetime | None] = mapped_column(TZDateTime)
    first_seen_at: Mapped[dt.datetime] = mapped_column(TZDateTime, nullable=False)
    # 协议字段①: last time we confirmed this posting live at the source.
    verified_at: Mapped[dt.datetime] = mapped_column(TZDateTime, nullable=False)
    delisted_at: Mapped[dt.datetime | None] = mapped_column(TZDateTime)
    relist_count: Mapped[int] = mapped_column(Integer, default=0)
    ghost_score: Mapped[float] = mapped_column(Float, default=0.0)  # 协议字段③
    # 协议字段④: v0.1 always NULL (only meaningful after employer claim).
    response_sla_days: Mapped[int | None] = mapped_column(Integer)
    # 协议字段②: employer_site | ats_public_api
    source: Mapped[str] = mapped_column(Text, nullable=False)
    # 协议字段⑤: always the employer's own apply URL.
    apply_channel: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Extraction provenance + rollback (v0.1 quality work) ---
    # Which extractor produced the current skills/remote/salary values.
    extraction_source: Mapped[str] = mapped_column(Text, default="heuristic")
    # The prior heuristic values, preserved so an LLM rebuild can be compared / rolled back.
    skills_fallback: Mapped[list[str]] = mapped_column(StringArray, default=list)
    remote_policy_fallback: Mapped[str | None] = mapped_column(Text)
    salary_min_fallback: Mapped[int | None] = mapped_column(Integer)
    salary_max_fallback: Mapped[int | None] = mapped_column(Integer)
    salary_currency_fallback: Mapped[str | None] = mapped_column(Text)


class Watch(Base):
    __tablename__ = "watches"
    # NO PII COLUMNS. EVER. (enforced by tests/test_privacy.py)

    watch_id: Mapped[str] = mapped_column(Text, primary_key=True)  # w_xxxx
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)  # anonymous, e.g. #a3f9
    filters: Mapped[dict] = mapped_column(JSONDict, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TZDateTime, default=_utcnow, server_default=func.now()
    )
    last_notified_at: Mapped[dt.datetime | None] = mapped_column(TZDateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Application(Base):
    __tablename__ = "applications"
    # NO PII COLUMNS. EVER. (enforced by tests/test_privacy.py)

    receipt_id: Mapped[str] = mapped_column(Text, primary_key=True)  # r_xxxx
    job_id: Mapped[str] = mapped_column(Text, ForeignKey("jobs.id"))
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    authorized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    delivered_via: Mapped[str] = mapped_column(Text, nullable=False)  # v0.1 always employer_site
    created_at: Mapped[dt.datetime] = mapped_column(
        TZDateTime, default=_utcnow, server_default=func.now()
    )
