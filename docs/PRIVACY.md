# OpenHire Privacy Policy

_Last updated: 2026-09-11 · Applies to the `openhire` package (PyPI), the `ohp` CLI, the MCP
server (stdio / sse / streamable-http), the Claude Desktop extension bundle, and the public
job snapshot published on GitHub Releases._

OpenHire is built so that it **cannot** collect personal data. This page states plainly what
is and is not processed. The guarantees below are enforced by automated tests in the
repository (`tests/test_privacy.py`, `tests/test_snapshot.py`), not by promise alone.

## 1. What we collect

**Nothing that identifies you.**

- There is **no résumé field** anywhere in the protocol. No tool accepts a file, a name, an
  email address, a phone number or a cover letter. A CI test fails the build if one is added.
- The only user-originated value the server ever stores is an **anonymous fingerprint**
  (e.g. `#a3f9`) that the client generates locally. The server cannot reverse it to a person.
- Skill matching runs **on your machine** (`ohp init --scan` reads your files locally and
  never uploads them). Only the resulting fingerprint and non-personal search filters
  (skills, remote preference, role family, salary floor) are sent to the server.

## 2. What the server stores and why

| Data | Where | Purpose | Contains PII? |
|---|---|---|---|
| Public job postings & employer records | Local SQLite index (or the host you connect to) | Search | No |
| Anonymous fingerprint + filter keys | Same index (`watches` table) | `watch_intent` / `check_watches` | No |
| Anonymous fingerprint + job id + authorization flag | Same index (`applications` table) | `authorize_application` record | No |

The public snapshot (`openhire-index.db.gz`) contains **only** the first row above; a test
refuses to install any snapshot whose user-state tables are non-empty.

## 3. Third parties

- Outbound network requests are made only to (a) employers' **public** ATS endpoints
  (Greenhouse, Lever, Ashby, Beisen, Moka) to read job postings, and (b) GitHub Releases to
  download the public snapshot.
- We do not use analytics, tracking pixels, advertising SDKs or telemetry of any kind.
- We never sell, share or transfer data to third parties. There is no data to sell.

## 4. Applications

`authorize_application` only **records** that you authorized an application and returns the
employer's own application URL. You apply as yourself, on the employer's site. OpenHire never
submits anything on your behalf and never receives what you submit there.

## 5. Retention and deletion

- Local mode: everything lives under `~/.openhire/` (or `OPENHIRE_HOME`). Delete that folder
  and nothing remains.
- Hosted mode (if you connect to a server someone else runs): the only records tied to you are
  keyed by your anonymous fingerprint. Because the fingerprint cannot be linked back to you,
  there is nothing to "look up"; rotate the fingerprint client-side and old records become
  orphaned.

## 6. Ranking is not for sale

Result order is a locked pure function of (match quality, freshness). No sponsored slots, no
bidding; the function signature is frozen by `tests/test_ranking.py`.

## 7. Contact

Questions or concerns: open an issue at
<https://github.com/gzchenhao/openhire/issues>. Maintainer: `@gzchenhao` on GitHub.
