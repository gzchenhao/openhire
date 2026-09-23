"""Skill-tag noise and extraction provenance (found 2026-09-23 while answering
"are there other defects?" after the persona test; reports/052).

The shared vocabulary claimed word-boundary matching and did not do it, and the ingest
path replaced skills without moving `extraction_source`, so a heuristic skill list could
wear a `deepseek` stamp. 3,098 live rows did.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire.db.models import Base, Company, Job
from openhire.pipeline import ingest
from openhire.pipeline.extract import ExtractionResult, HeuristicExtractor, extract_skills
from openhire.pipeline.ingest import IngestStats
from openhire.ats.base import JobRecord

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 23, tzinfo=UTC)


# --- 1. the vocabulary matches words, not substrings --------------------------------------
def test_trust_is_not_rust_and_scalable_is_not_scala():
    tags = extract_skills("We value trust and build scalable systems for our customers.")
    assert "rust" not in tags and "scala" not in tags, tags


def test_real_mentions_still_match():
    tags = extract_skills("Senior Rust engineer; Scala services; React.js frontends; modern C++ and CUDA.")
    assert {"rust", "scala", "react", "c++", "cuda"} <= set(tags), tags


def test_boundaries_do_not_break_symbol_tags():
    assert "c++" in extract_skills("C++17 on Linux.")
    assert {"python", "java", "cuda"} <= set(extract_skills("Python3, Java8 and CUDA12 experience."))
    assert "node" in extract_skills("Node.js services")
    assert "postgres" in extract_skills("PostgreSQL and Redis")


# --- 2. the stamp says who answered, not who was asked -------------------------------------
class _AskedLLMGotHeuristic:
    """An LLM extractor whose call fails and degrades, exactly like the real ones."""

    name = "deepseek"

    def extract(self, job: JobRecord) -> ExtractionResult:
        return HeuristicExtractor().extract(job)  # what every LLM path does on failure


def _rec(title: str, desc: str) -> JobRecord:
    return JobRecord(
        ats_job_id="1", title=title, description_raw=desc, location="Beijing",
        apply_channel="https://app.mokahr.com/apply/x/1#/job/1", posted_at=NOW,
    )


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = Session(engine, future=True)
    s.add(Company(id="x", name="X", ats_vendor="moka", ats_tenant="x", careers_url="u",
                  verified=False, last_crawled_at=NOW))
    s.commit()
    return s


def test_fallback_result_carries_the_heuristic_stamp():
    res = _AskedLLMGotHeuristic().extract(_rec("Rust Engineer", "Rust, Kafka."))
    assert res.extractor == "heuristic"


def test_ingest_stamps_the_extractor_that_answered():
    s = _session()
    company = s.get(Company, "x")
    rec = _rec("Rust Engineer", "You will write Rust and run Kafka.")
    stats = IngestStats()
    ingest._insert_new_job(s, company, rec, "x:1", "h1", _AskedLLMGotHeuristic(), stats, NOW, {})
    s.commit()
    job = s.get(Job, "x:1")
    assert job.extraction_source == "heuristic", "asked deepseek, heuristic answered"
    assert "rust" in job.skills


def test_update_moves_the_stamp_with_the_skills():
    s = _session()
    company = s.get(Company, "x")
    rec = _rec("Rust Engineer", "You will write Rust.")
    ingest._insert_new_job(s, company, rec, "x:1", "h1", HeuristicExtractor(), IngestStats(), NOW, {})
    s.commit()
    job = s.get(Job, "x:1")
    job.extraction_source = "deepseek"  # pretend the monthly LLM pass enriched it
    job.skills = ["rust", "distributed-systems"]
    s.commit()
    # Content changes; the weekly crawl re-extracts with the heuristic.
    rec2 = _rec("Rust Engineer", "You will write Rust and Kafka consumers.")
    ingest._update_job(job, rec2, "h2", HeuristicExtractor(), IngestStats(), NOW)
    s.commit()
    assert job.extraction_source == "heuristic"
    assert "kafka" in job.skills
