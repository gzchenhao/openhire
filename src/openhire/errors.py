"""Protocol errors — ERR_UPPER_SNAKE code + one plain-language sentence (design §Errors)."""

from __future__ import annotations


class OpenHireError(Exception):
    """An error surfaced to the agent/CLI with a stable machine code."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict:
        return {"error": self.code, "message": self.message}
