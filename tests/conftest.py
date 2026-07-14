"""Test configuration.

Point the *global* database at a throwaway SQLite file BEFORE any openhire module reads
config, and force the offline heuristic extractor. Tests that need an isolated DB build
their own in-memory engines; the MCP acceptance tests use this global temp DB.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="openhire-test-"))
os.environ["OPENHIRE_HOME"] = str(_TMP)
os.environ["OPENHIRE_DATABASE_URL"] = f"sqlite+pysqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["OPENHIRE_EXTRACTOR"] = "heuristic"
os.environ.pop("OPENHIRE_ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
