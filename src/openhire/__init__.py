"""OpenHire v0.1 「哨兵」— an MCP job protocol layer for AI agents.

Résumés never leave your device. Only an anonymous fingerprint ever transits the
server. See the three privacy red lines in README / tests/test_privacy.py.
"""

try:  # single source of truth is pyproject; never hardcode a second copy
    from importlib.metadata import PackageNotFoundError, version as _pkg_version

    __version__ = _pkg_version("openhire")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+dev"
