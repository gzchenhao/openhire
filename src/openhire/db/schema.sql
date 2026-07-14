-- OpenHire v0.1 — canonical schema (PostgreSQL 15+).
-- This is the source of truth for the data contract. The SQLAlchemy models in
-- models.py mirror this exactly and degrade to SQLite for local development.
--
-- The "五协议字段" (five protocol fields) on `jobs` are load-bearing and MUST NOT
-- be dropped: verified_at, source, ghost_score, response_sla_days, apply_channel.
--
-- PRIVACY RED LINE #1: `applications` and `watches` MUST NOT contain any PII column.
-- Identity is an anonymous, client-generated fingerprint (e.g. #a3f9). Forever.

CREATE TABLE companies (
  id              TEXT PRIMARY KEY,           -- slug
  name            TEXT NOT NULL,
  ats_vendor      TEXT NOT NULL,              -- greenhouse | lever | ashby
  ats_tenant      TEXT NOT NULL,
  careers_url     TEXT,
  verified        BOOLEAN DEFAULT FALSE,      -- v0.3 employer-claim; field reserved
  last_crawled_at TIMESTAMPTZ
);

CREATE TABLE jobs (
  id               TEXT PRIMARY KEY,          -- {company_id}:{ats_job_id}
  company_id       TEXT REFERENCES companies(id),
  title            TEXT NOT NULL,
  description_raw  TEXT,
  skills           TEXT[] DEFAULT '{}',       -- LLM-extracted, lowercase-normalized
  remote_policy    TEXT,                      -- remote | hybrid | onsite | unknown
  salary_min       INT,
  salary_max       INT,
  salary_currency  TEXT,
  salary_inferred  BOOLEAN DEFAULT FALSE,
  location         TEXT,
  first_seen_at    TIMESTAMPTZ NOT NULL,
  verified_at      TIMESTAMPTZ NOT NULL,      -- 协议字段①: last confirmed live at source
  delisted_at      TIMESTAMPTZ,
  relist_count     INT DEFAULT 0,
  ghost_score      REAL DEFAULT 0,            -- 协议字段③
  response_sla_days INT,                      -- 协议字段④ (v0.1 always NULL)
  source           TEXT NOT NULL,             -- 协议字段②: employer_site | ats_public_api
  apply_channel    TEXT NOT NULL,             -- 协议字段⑤: always the employer's own apply URL
  content_hash     TEXT NOT NULL,

  -- Extraction provenance + rollback: which extractor set the current skills/remote/
  -- salary, and the prior heuristic values kept for comparison / rollback.
  extraction_source        TEXT DEFAULT 'heuristic',
  skills_fallback          TEXT[] DEFAULT '{}',
  remote_policy_fallback   TEXT,
  salary_min_fallback      INT,
  salary_max_fallback      INT,
  salary_currency_fallback TEXT
);

CREATE INDEX idx_jobs_company        ON jobs (company_id);
CREATE INDEX idx_jobs_live           ON jobs (delisted_at);
CREATE INDEX idx_jobs_remote         ON jobs (remote_policy);
CREATE INDEX idx_jobs_verified_at    ON jobs (verified_at);

CREATE TABLE watches (
  watch_id         TEXT PRIMARY KEY,          -- w_xxxx
  fingerprint      TEXT NOT NULL,             -- anonymous, client-generated, e.g. #a3f9
  filters          JSONB NOT NULL,            -- { skills[], remote, min_salary, ... }
  created_at       TIMESTAMPTZ DEFAULT now(),
  last_notified_at TIMESTAMPTZ,
  active           BOOLEAN DEFAULT TRUE
  -- NO PII COLUMNS. EVER.
);

CREATE TABLE applications (
  receipt_id       TEXT PRIMARY KEY,          -- r_xxxx
  job_id           TEXT REFERENCES jobs(id),
  fingerprint      TEXT NOT NULL,
  authorized       BOOLEAN NOT NULL,          -- must be TRUE to be written
  delivered_via    TEXT NOT NULL,             -- v0.1 always employer_site
  created_at       TIMESTAMPTZ DEFAULT now()
  -- NO PII COLUMNS. EVER.
);
