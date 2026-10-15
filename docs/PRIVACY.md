# OpenHire Privacy Policy

_Last updated: 2026-10-15 · Applies to the `openhire` package (PyPI), the `ohp` CLI, the MCP
server (stdio / sse / streamable-http), the Claude Desktop extension bundle, the public
job snapshot published on GitHub Releases, and the hosted endpoint the maintainer runs._

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
  (Greenhouse, Lever, Ashby, Beisen, Moka) and first-party employer career-site mirrors
  (currently Li Auto: `www.lixiang.com` and `api-web.lixiang.com`) to read job postings,
  and (b) GitHub Releases to download the public snapshot.
- `check_employer` (v0.8.0) sends the **company's** name or domain to RDAP (rdap.org), the Internet
  Archive (web.archive.org) and the company's own homepage, and to 天眼查's API only when you set
  `TIANYANCHA_API_KEY` on your own machine (your account pays, your machine holds the key, we never
  see either). Nothing about you is sent, and nothing fetched is stored in the index or snapshot.
- `check_employer` (v0.8.4) also downloads the public OFAC sanctions lists (CSV files from
  treasury.gov) to your machine at most once a day and matches the company's name there; the
  name is not sent to any sanctions service.
- `check_employer` (v0.8.8) also downloads EarlyTip's public file of organisational and financing
  events (`https://earlytip.com/data/org_events.json`) to your machine at most once a day and
  matches the company's name there; EarlyTip sees an ordinary download, never the name. What is
  shown is the event type, a date, the amount where recorded, the source domain and a plain link to the source page.
- `read_board` (v0.8.3) sends only the board's tenant (the part of a careers URL after the
  vendor's host) to that vendor's public endpoint, the same request the weekly crawl makes.
  Nothing about you is sent, and nothing read is stored.
- **Hosted endpoint** (v0.8.11): the maintainer runs a copy of this server at
  `https://gzchenhao-openhire.hf.space/mcp` (a Hugging Face Space built from `hosted/`) for
  clients that can only reach a URL, such as ChatGPT connectors. It receives exactly what the
  tools take (search filters, a company name or domain, a board URL, your anonymous
  fingerprint) and nothing else; it keeps no log of queries (access logging is off); watches
  and application records are stored in its index keyed by your fingerprint, carried over when
  the index is refreshed, and lost if the host is rebuilt; requests are rate-limited per
  address. `check_employer` and `read_board` make their outbound requests from that host
  instead of from your machine, with private address space refused. Hugging Face, as the
  platform, sees the connection as it sees any web request. If any of this matters to you,
  run OpenHire locally: there, nothing of a search leaves your machine.
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
