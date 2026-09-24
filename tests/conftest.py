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

import pytest  # noqa: E402  (after the environment is set, on purpose)


@pytest.fixture(scope="session", autouse=True)
def _never_the_real_index():
    """Refuse to run if the package resolved its database before this file set the env.

    Several tests seed by deleting every row (tests/test_role_group_and_paging.py) and call
    init_db() on whatever URL openhire.config holds. On 2026-09-23 a run reached the user's
    real index at ~/.openhire/openhire.db and left one test row in place of 16,381
    postings. This fails the whole session loudly instead."""
    from openhire import config

    assert "openhire-test-" in config.DATABASE_URL, (
        f"tests would run against {config.DATABASE_URL}; openhire.config was imported "
        "before conftest set OPENHIRE_DATABASE_URL"
    )
    yield
