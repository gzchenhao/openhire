"""Employer verification: facts an employer did not supply, for maintainers and seekers.

`checks` holds the individual checks (pure and one-GET network ones); `tianyancha` the
optional paid register lookup with the seeker's own key; `employer_check` assembles the
checklist the `check_employer` MCP tool returns. A checklist is a list of facts with
sources and times. It is never a score and never a verdict (reports/065).
"""

from . import checks, tianyancha
from .employer_check import build_checklist

__all__ = ["checks", "tianyancha", "build_checklist"]
