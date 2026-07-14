"""Content hashing + text normalization for change/relist detection."""

from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def normalize_text(s: str | None) -> str:
    """Lowercase, collapse whitespace — the canonical form used for hashing."""
    if not s:
        return ""
    return _WS.sub(" ", s.strip().lower())


def content_hash(title: str, description: str) -> str:
    """sha256 over normalized title + description (README §变更检测)."""
    basis = normalize_text(title) + "\n" + normalize_text(description)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def normalize_title(title: str | None) -> str:
    """Aggressive title normalization for relist detection: drop punctuation too,
    so 'Sr. LLM Engineer' and 'Sr LLM Engineer' collapse together."""
    return _WS.sub(" ", _PUNCT.sub(" ", normalize_text(title))).strip()
