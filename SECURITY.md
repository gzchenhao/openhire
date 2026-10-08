# Security Policy

OpenHire runs on your own machine and stores nothing that identifies you
(see [docs/PRIVACY.md](docs/PRIVACY.md)). Even so, it reads data from the
public internet and writes a local SQLite file, so bugs with a security
impact are possible. This page says how to tell us.

## Supported versions

Only the latest release on PyPI is supported. Fixes ship as a new version;
we do not backport. Check yours with `ohp version`.

| Version | Supported |
|---|---|
| latest `0.6.x` | yes |
| anything older | no, please upgrade (`uvx openhire@latest serve` always runs the latest) |

## Reporting a vulnerability

Please do **not** open a public issue for anything that could put users at
risk (for example: a way to make the server read or send a local file, a way
for a job posting to run code on the user's machine, a snapshot that could be
swapped for a malicious one, or a privacy guarantee in `docs/PRIVACY.md` that
does not hold).

Use GitHub's private channel instead:

**https://github.com/gzchenhao/openhire/security/advisories/new**

Only the maintainer can read it. If you cannot use GitHub, email
**gdchenhao@qq.com** with "Security" in the subject.

What helps: the version (`ohp version`), the tool or command involved, the
steps to reproduce, and what you believe the impact is. A proof of concept
is welcome; please do not test against real employers' systems beyond what
reproducing the issue requires, and never with a real résumé.

## What to expect

- Acknowledgement within 3 days.
- An assessment and, if confirmed, a fix plan within 14 days. Most fixes ship
  as a patch release on PyPI the same day they are merged, with the advisory
  published alongside.
- Credit in the release notes if you want it.

## Scope notes

- **In scope:** the `openhire` package, the `ohp` CLI, the MCP server in all
  transports, the Claude Desktop bundle (`.mcpb`), the plugin manifests, the
  snapshot build and refresh workflows, and the published snapshot.
- **Out of scope:** the employers' own ATS endpoints and career sites that
  OpenHire reads from. Please report problems there to the employer.
- **Not a vulnerability:** a posting that is stale, mis-tagged or missing.
  That is a data-quality report; open a normal issue.

## Our side of the bargain

Privacy guarantees are enforced by tests in CI (`tests/test_privacy.py`,
`tests/test_snapshot.py`), not by promise. Secret scanning and push protection
are on for this repository. The launchers pin the exact OpenHire release
(`mcpb/pyproject.toml`, the plugin `.mcp.json`), so an install runs the
version that was tested, not whatever is newest.
