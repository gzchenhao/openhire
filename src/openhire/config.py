"""Runtime configuration for OpenHire.

Everything is environment-driven so the same code runs on a laptop (SQLite) and in
production (Postgres). No secrets are ever committed; the Anthropic key is injected
via OPENHIRE_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY only when LLM extraction runs.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Storage -----------------------------------------------------------------
# Client-side state lives under ~/.openhire (fingerprint, config, receipts).
CLIENT_HOME = Path(os.environ.get("OPENHIRE_HOME", Path.home() / ".openhire"))

# Default local dev database is a SQLite file next to the client state. Point
# OPENHIRE_DATABASE_URL at a Postgres DSN for production
# (e.g. postgresql+psycopg://user:pass@host/openhire).
_DEFAULT_SQLITE = CLIENT_HOME / "openhire.db"
DATABASE_URL = os.environ.get(
    "OPENHIRE_DATABASE_URL",
    f"sqlite+pysqlite:///{_DEFAULT_SQLITE.as_posix()}",
)

# --- Crawl politeness ---------------------------------------------------------
# Never hit the same tenant more than once per this window.
MIN_TENANT_INTERVAL_MINUTES = int(os.environ.get("OPENHIRE_MIN_TENANT_INTERVAL_MIN", "30"))
# Global cap on concurrent outbound ATS requests.
MAX_GLOBAL_CONCURRENCY = int(os.environ.get("OPENHIRE_MAX_CONCURRENCY", "5"))
HTTP_TIMEOUT_SECONDS = float(os.environ.get("OPENHIRE_HTTP_TIMEOUT", "30"))
USER_AGENT = os.environ.get(
    "OPENHIRE_USER_AGENT",
    "openhire/0.1 (+https://openhire.dev; public-ATS-reader; contact via github)",
)

# Bootstrap snapshot (public jobs/companies only) — a GitHub Release asset, NOT in the
# wheel. `ohp bootstrap` downloads this then refreshes it live. Override for testing.
SNAPSHOT_URL = os.environ.get(
    "OPENHIRE_SNAPSHOT_URL",
    "https://github.com/gzchenhao/openhire/releases/download/v0.1.0/openhire-index.db.gz",
)

# --- Freshness tiers ----------------------------------------------------------
# Companies with a change in the last N days are polled on the hot cadence.
FRESHNESS_HOT_WINDOW_DAYS = int(os.environ.get("OPENHIRE_HOT_WINDOW_DAYS", "7"))
FRESHNESS_HOT_INTERVAL_HOURS = int(os.environ.get("OPENHIRE_HOT_INTERVAL_HOURS", "6"))
FRESHNESS_COLD_INTERVAL_HOURS = int(os.environ.get("OPENHIRE_COLD_INTERVAL_HOURS", "24"))

# --- LLM extraction -----------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("OPENHIRE_ANTHROPIC_API_KEY") or os.environ.get(
    "ANTHROPIC_API_KEY"
)
# Which extractor to use: "auto" | "anthropic" | "deepseek" | "heuristic".
EXTRACTOR = os.environ.get("OPENHIRE_EXTRACTOR", "auto")
EXTRACTION_MODEL = os.environ.get("OPENHIRE_EXTRACTION_MODEL", "claude-haiku-4-5-20251001")

# DeepSeek (OpenAI-compatible) — cheap backend for the simple skills/remote/salary task.
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.environ.get("OPENHIRE_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("OPENHIRE_DEEPSEEK_MODEL", "deepseek-chat")

# JD text is capped before extraction to bound token cost (skills/remote sit early in a JD).
EXTRACTION_JD_CHAR_CAP = int(os.environ.get("OPENHIRE_JD_CHAR_CAP", "4000"))

# DeepSeek deepseek-chat list price in CNY per 1M tokens (cache-miss input / output).
# Used only for budget reporting + the hard cost ceiling; override if pricing changes.
DEEPSEEK_PRICE_INPUT_CNY = float(os.environ.get("OPENHIRE_DEEPSEEK_PRICE_IN", "2.0"))
DEEPSEEK_PRICE_OUTPUT_CNY = float(os.environ.get("OPENHIRE_DEEPSEEK_PRICE_OUT", "8.0"))
# Hard stop: the rebuild halts and asks before spending beyond this (CNY).
EXTRACTION_COST_CEILING_CNY = float(os.environ.get("OPENHIRE_COST_CEILING_CNY", "50.0"))


def ensure_client_home() -> Path:
    CLIENT_HOME.mkdir(parents=True, exist_ok=True)
    return CLIENT_HOME
