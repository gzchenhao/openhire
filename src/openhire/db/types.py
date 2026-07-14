"""Dialect-aware column types.

The canonical schema (schema.sql) targets Postgres and uses TEXT[], JSONB and
TIMESTAMPTZ. These decorators let the identical ORM run on SQLite for local dev by
storing arrays/objects as JSON text, while emitting the native Postgres types when
connected to Postgres.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import JSON, DateTime, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.types import TypeDecorator


class StringArray(TypeDecorator):
    """``TEXT[]`` on Postgres, JSON-encoded list on SQLite."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text))
        return dialect.type_descriptor(Text)

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            value = []
        if dialect.name == "postgresql":
            return list(value)
        return json.dumps(list(value))

    def process_result_value(self, value: Any, dialect) -> list[str]:
        if value is None:
            return []
        if dialect.name == "postgresql":
            return list(value)
        return json.loads(value)


class JSONDict(TypeDecorator):
    """``JSONB`` on Postgres, ``JSON`` (text) on SQLite."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class TZDateTime(TypeDecorator):
    """Timezone-aware UTC datetime that behaves identically on Postgres and SQLite.

    SQLite has no native tz type and returns naive datetimes; this normalizes every
    value to aware-UTC on both bind and result, so the app never mixes naive/aware
    datetimes regardless of backend (maps to TIMESTAMPTZ on Postgres).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value

    def process_result_value(self, value: Any, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value
