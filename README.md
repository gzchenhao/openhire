<!-- mcp-name: io.github.gzchenhao/openhire -->

# OpenHire · 开聘

> **A job-search radar for your AI assistant — first-party listings, every posting's real age, and your résumé never touches our servers.**
> 让 AI 助手替你盯岗的求职雷达 —— 一手职位、岗位在架时长打分，简历不经过我们的服务器。

![MCP 1.0](https://img.shields.io/badge/MCP-1.0-58A6FF) ![privacy: local-first](https://img.shields.io/badge/privacy-local--first-3FB950) ![python ≥ 3.11](https://img.shields.io/badge/python-%E2%89%A5%203.11-C9D1D9) ![license: MIT](https://img.shields.io/badge/license-MIT-C9D1D9) ![139 employers hiring](https://img.shields.io/badge/employers%20hiring-139-E3B341) [![OpenHire on Glama](https://glama.ai/mcp/servers/gzchenhao/openhire/badges/score.svg)](https://glama.ai/mcp/servers/gzchenhao/openhire)

<p align="center"><img src="docs/quickstart.svg" alt="30-second quickstart: pipx install openhire, ohp bootstrap, ohp search" width="880"></p>
<p align="center"><sub>Real terminal output — install from PyPI, download the public index, search. No account, no signup.</sub></p>

> **Is your company in here, and you did not put it here?**
> Your postings are in this index because your own careers page serves them publicly. We
> can measure how long a role has been open; we cannot see why, and a long-open role is a
> question, not a verdict. [Claim your company](#for-employers-claim-your-tenant) — free,
> no payment, ever — and say why in your own words, or ask us to remove you and we will,
> without arguing.
> 贵司被收录了、而且不是贵司提交的？[点这里认领](#for-employers-claim-your-tenant)，免费，
> 可以用自己的话解释，也可以直接要求我们移除。

### What your agent actually sees

You ask your assistant a question in plain language. It calls `search_jobs`, and every row comes
back carrying the employer's **real** posting date — so the agent can reason about staleness
instead of guessing.

> **You:** *Any senior Python roles that are actually still open? Skip the stale ones.*

```jsonc
// one row from search_jobs — trimmed to the fields that matter here
{
  "title":        "Senior Python Engineer",
  "company":      "MongoDB",
  "datePosted":   "2026-03-31",   // from the employer's ATS, not a board's refreshed label
  "days_open":    166,
  "ghost_score":  0.61,           // pure f(relist_count, datePosted) — frozen by a test
  "apply_channel":"https://boards.greenhouse.io/…",   // straight to the employer
  "verified_at":  "2026-09-02T09:47:10Z"
}
```

> **Assistant:** *This one has been open 166 days with a ghost_score of 0.61 — I'd deprioritise it.
> Here are four posted in the last three weeks instead…*

`ghost_score` measures **how long a posting has been open**, not whether the employer still intends
to hire. A long-open role can equally mean "hard to fill". Treat it as a reason to ask, not a verdict.

---

An MCP server that turns **any** MCP-speaking assistant — Claude, Cursor, Windsurf, Cline,
ChatGPT via connectors — into a private radar for
**AI / Infra, autonomous-driving and embodied-AI jobs** — pulled straight from **139 employers'**
own career sites and public ATS APIs (Greenhouse / Lever / Ashby / 北森 Beisen / Moka), across
the US, Europe **and China** (Waymo, Figure, Zoox — and Unitree, XPeng, UBTECH, Mech-Mind…).
**No account. No signup. No résumé upload. Ever.**

Three things a job board won't do for you:

- **Surfaces how long each role has really been open.** Every listing carries a `ghost_score` aged off the employer's
  **real** posting date — the "2 days ago" a board shows you can be 300 days old in the ATS.
- **Structural privacy, not a pinky-promise.** There is no résumé field in the protocol; a CI
  test fails the build if anyone adds one. Matching runs on your machine — only an anonymous
  fingerprint reaches the server.
- **Ranking you can't buy.** Order is a locked pure function of (match, freshness). No
  sponsored slots, no bidding — the signature is frozen by a test.

This is the 「哨兵 / Sentinel」 reference implementation — see
`design_handoff_openhire_v01/README.md` for the full protocol spec.

---

## Quickstart — under a minute

```bash
# 1. Install (pipx keeps it isolated and puts `ohp` on your PATH)
pipx install openhire

# 2. Get a job index. Downloads the public snapshot (~25 MB), then runs one incremental
#    crawl to refresh verified_at / delisting. The crawl is the slow part: it prints one
#    line per employer and can run 20+ minutes on a cold index.
#    Only needed for the CLI — `ohp serve` fetches the snapshot by itself on first start.
ohp bootstrap                    # 139 employers · ~16k live postings · no account

# 3. Use it directly…
ohp search --required-skills rust,k8s --remote --role-family engineering
ohp search --currency CNY --role-family engineering   # e.g. CN autonomous-driving / robotics roles

# …or connect it to an MCP client:
ohp serve
```

Then point your MCP client at it — see **[Works with](#works-with)** below.

---

## Works with

All clients use the same MCP entry. The config below works in every MCP client and pulls
the package on demand — but it does need [uv](https://docs.astral.sh/uv/) present first.

> **New to MCP? Two shortcuts before the config below.**
> **Claude Desktop** — download [`openhire-0.6.0.mcpb`](https://github.com/gzchenhao/openhire/releases/latest)
> and double-click it. No terminal, no Python.
> **Cursor / Claude Code** — paste this to your agent: *"Install the MCP server at
> github.com/gzchenhao/openhire. Install `uv` first if it is missing, then add
> `uvx openhire@latest serve` to my MCP config and tell me which file you changed."*

**Prerequisite:** `uvx` ships with [uv](https://docs.astral.sh/uv/). Without it the config
below fails with nothing but "server failed to start" in your client — install uv first:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # macOS / Linux
irm https://astral.sh/uv/install.ps1 | iex          # Windows PowerShell
```

```json
{ "mcpServers": { "openhire": { "command": "uvx", "args": ["openhire@latest", "serve"] } } }
```

First start downloads a ~25 MB index in the background; searches fill in within a few minutes.

**What `uvx` costs you, every time.** `uvx` resolves the package on each invocation — measured
at **7–8 s** per call even with a warm cache. That is paid on every MCP session start and every
CLI command. It buys you never having to manage an install. If you would rather pay once:

```bash
pipx install openhire     # then use "command": "ohp", "args": ["serve"] — process-start latency
```

`@latest` also means your tool surface can change under you without warning. Pin it when that
matters: `"args": ["openhire==0.6.0", "serve"]`.

The server **auto-downloads the public job snapshot on first run** if the index is empty, so
`ohp bootstrap` is optional. If you ran `pipx install openhire`, `"command": "ohp"` works too.

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`); quit & reopen after editing:
```json
{ "mcpServers": { "openhire": { "command": "ohp", "args": ["serve"] } } }
```

**Cursor** — `~/.cursor/mcp.json` (or a project `.cursor/mcp.json`):
```json
{ "mcpServers": { "openhire": { "command": "uvx", "args": ["openhire", "serve"] } } }
```

**Windsurf** — `~/.codeium/windsurf/mcp_config.json`:
```json
{ "mcpServers": { "openhire": { "command": "uvx", "args": ["openhire", "serve"] } } }
```

> First start downloads the ~25 MB public snapshot (jobs/companies only) — give it a moment.
> To refresh later run `ohp bootstrap --force` or `ohp ingest`. On Windows Claude Desktop from
> the Microsoft Store, the config is under `…\Packages\<Claude package>\LocalCache\Roaming\Claude\`.
>
> **Hosted / remote:** `ohp serve --transport streamable-http --host 0.0.0.0 --port 8000`
> exposes `http://host:8000/mcp` (also `--transport sse`). A `Dockerfile` is included.

---

## What it does

| Tool | What it gives you |
|------|-------------------|
| `search_jobs` | Hard-filter the live index; every result carries `verified_at`, `datePosted`, `days_open`, `ghost_score`, `remote_scope`, `eligible_regions`, `apply_channel`. Filter by `required_skills` (AND), `role_family`, `remote_scope`, `min_salary` + `currency`. |
| `watch_intent` | Register a standing intent once — new matching jobs are waiting next time you check, even after you close the terminal. Accepts `required_skills` / `role_family` so sales / solutions roles stay out. |
| `check_watches` | Pull the matches that are new since your last check (client-pull; stdio has no push). |
| `authorize_application` | One explicit confirmation per job. It records your authorization and returns the employer's **own** application URL — you apply as yourself. It **cannot** accept a résumé. |
| `get_company_info` | Aggregate, anonymous trust signals for one employer (`ghost_score_avg`, `active_jobs`, `index_built_at`). Never any candidate data. |

Optional, entirely local: `ohp init --scan <dir>` derives a **skill fingerprint** from your
own repos. You never write a résumé; the code never leaves your machine — only an anonymous
vector does.

### For employers: claim your tenant

If your company is in this index, the listings came from your own public ATS — we did not
ask, because we did not need to. What we cannot know is your side of it: whether a role is
an evergreen talent pool rather than a stale req, or how fast you actually reply.

[Claim it](https://github.com/gzchenhao/openhire/issues/new?template=employer_claim.yml)
（[中文表单](https://github.com/gzchenhao/openhire/issues/new?template=employer_claim_zh.yml)）.
Free, verified by corporate identity — a GitHub org membership or a reply from a corporate
domain — and **never by payment**. We answer within 3 business days, claiming leads to no
paid follow-up of any kind, and your proof is used to verify and then nothing else.

No GitHub account? **Email gdchenhao@qq.com** with "Employer claim" and your company name in the
subject — sending from your corporate domain is itself the verification — or have anyone
file the form on your behalf, since what we verify is the company and not the filer.
没有 GitHub 账号？**直接发邮件到 gdchenhao@qq.com**，用贵司企业邮箱发出来即完成身份核验。

A claim gets you:

- **Your own note, attributed to you, beside the roles you name.** We can see how long a
  role has been open; we cannot see why. An evergreen talent pool, a genuinely hard-to-fill
  role, and a neglected one look identical from outside, and only you can tell them apart.
- `evergreen` / `hard to fill` / `closed` status on specific titles. A `closed` role stays
  visible while your ATS still serves it — we do not hide what your own site returns — but
  it is marked closed on your word so nobody else applies.
- A correction if your ATS's date field means "requisition opened", not "went live". That
  one misreading makes every role you have look years old, and it is not your fault.
- `response_sla_days` on every one of your postings, including ones you post later
- `claimed: true` on your company, with the date

It does **not** get you rank, and it does **not** lower your `ghost_score`. Ordering is a
locked pure function of (match, freshness) and the score is a pure function of (relist
count, posting age); tests freeze both and assert the claim path touches neither. Your note
sits beside the score and explains it. We would rather show a high score with your
explanation than a quiet score somebody paid for.

Asking to be removed entirely is also fine, and we will not argue about it.

Verified claims live in [`src/openhire/seed/claims.py`](src/openhire/seed/claims.py) — in
the repo, not in a private database — so each one is a reviewable diff, and the weekly
rebuild re-applies them instead of quietly dropping them.

### Keeping it current

The index refreshes weekly, so a search can be up to seven days behind. When the user is
about to act on one employer and wants today's truth:

```bash
ohp refresh unitree          # ~1 minute · at most one crawl per employer per 6 hours
```

Over MCP this is the `refresh_index` tool. Three rules are built in, not advisory:

* **One employer per call.** A full crawl is 20+ minutes and no client waits that long. An
  ambiguous word (`robot` → 11 matches) is refused with the candidate list, never fanned out.
* **Six-hour throttle per employer**, checked *before* any network call, so a too-soon
  request costs the ATS nothing and returns `last_refreshed_at` instead of an error.
* **Not for speculative or looped calls.** Each one hits somebody else's public endpoint.

That last point is the whole design constraint: our own crawl is a weekly batch we control,
and handing refresh to callers turns it into *our users* hitting *their* endpoint on our
behalf. The throttle is what keeps that boundary ours to keep rather than ours to spend.

### Reading the three dates

Every row carries three timestamps that answer three different questions. Read together they
separate an abandoned requisition from one somebody is still tending:

| field | question it answers |
|---|---|
| `verified_at` | did the employer's ATS still return this the last time we looked? |
| `datePosted` / `days_open` | how long has it been open? `ghost_score` ages off this |
| `updated_at` / `days_since_update` | when did the employer last touch it? **Null when their ATS does not report one** (Ashby, Lever and Beisen do not; Greenhouse and Moka do) — read null as "unknown", never as "abandoned" |

`ghost_score = 1.0` alone is not a verdict. Open 367 days and untouched for 367 days reads as
abandoned; open 327 days but touched 13 days ago reads as a tended evergreen req. Among the rows where the ATS actually reports a last-touched date,
**75% of `ghost_score >= 0.99` postings were touched by the employer within the last 30 days** (measured 2026-09-15).
`ghost_reason` spells out which input drove the score ("age only: open 367d, never relisted").

None of these measure intent. A long-open role can equally mean hard-to-fill — treat the
numbers as a reason to ask, not a verdict.

### Asking about one employer

`search_jobs(company=...)` takes whatever the user actually said — an id (`unitree`), or any
part of the name in either language (`宇树`, `Unitree`, `XPeng`). A name this index does not
carry comes back as the empty-result object naming the company, never as an unfiltered search.

```bash
ohp search --company 宇树 --role-family engineering
ohp search --company waymo --distinct          # one row per role, not one per city
```

`--distinct` (`collapse_role_group` over MCP) keeps one row per `role_group` and adds
`role_group_size`. About 20% of a page is the same role listed once per city; folding is
opt-in because each city row has its own `job_id` and `apply_channel`, which matters under a
location or visa constraint.

## The five protocol fields

Every listing is valid `schema.org/JobPosting`, plus:

- `verified_at` — last moment confirmed live on the employer's own site
- `source` — `employer_site | ats_public_api` (never a job board)
- `ghost_score` — 0–1 listing-activity signal, aged off the **real** posting date (lower =
  fresher). A noise filter, not an accusation: long-open listings are often evergreen talent
  pools or slow pipelines — the score simply lets agents down-rank low-activity noise
- `response_sla_days` — the employer's OWN committed reply window. **Null on almost every
  row, and that null is meaningful**: it is set only when an employer claims their tenant.
  We never infer or estimate it, because we cannot observe a reply even in principle — the
  application deep-links to the employer and never touches this server. Read null as "no
  employer has claimed this tenant", not as "missing" or "slow".
  [Employers: claim yours](https://github.com/gzchenhao/openhire/issues/new?template=employer_claim.yml)
  — free, verified by corporate identity, never by payment. It buys a verified badge, the
  ability to correct listing status (an evergreen pool carrying an unfair staleness score,
  say), and this field. It does not buy rank: ranking is a locked pure function of
  (match, freshness), and a test freezes that signature.
- `apply_channel` — always the employer's own application URL, deep-linked to the specific job

## Privacy Policy

Short version: **there is no résumé field in the protocol**, matching runs on your machine, and
the only user-originated value the server ever stores is an anonymous client-generated
fingerprint. No analytics, no telemetry, no third-party sharing. Full policy:
[docs/PRIVACY.md](https://github.com/gzchenhao/openhire/blob/main/docs/PRIVACY.md).

## Privacy model

| | |
|---|---|
| **Résumé / PII upload** | **never** — matching runs locally; a résumé never transits the server, and we never store one |
| **What the server sees** | one anonymous, client-generated fingerprint + hard filters |
| **Repo scan** | local-only · personal projects · explicit consent · opt-out anytime |
| **Job sources** | first-party only: employer career pages + public ATS APIs (Greenhouse / Lever / Ashby) |

## First-run data — the snapshot vs. fresh

`ohp bootstrap` (default) downloads a small **public** index snapshot (a GitHub Release
asset — `companies` + `jobs` only, **zero** user data) and then runs one incremental crawl to
refresh `verified_at` / delisting. `--fresh` skips the snapshot and crawls the public ATS from
scratch with the free offline heuristic extractor. Either way: no account, no PII.

Two things that surprise people:

- **The incremental crawl is slow and quiet.** On a cold index it can run for 20+ minutes
  with no output. It is working, not hung. If you only want the data, `ohp serve` skips it
  entirely — the server downloads the snapshot on first start and is answering in seconds.
- **The snapshot URL is pinned to the `v0.1.0` tag on purpose.** It looks stale; it is not.
  That asset is overwritten in place every Monday by a scheduled workflow, so the URL is a
  stable address for always-current data. Pinning it to the newest tag would break every
  client the moment a release is cut.

## Three rules this project will never break

1. Your résumé stays on your machine — it never transits the server, and we never store it.
2. Ranking is not for sale — it is only `f(match_quality, freshness)`, a locked pure function.
3. Employers pay only for authorized, delivered outcomes — never for exposure. (v0.1 has no
   billing at all.)

These are enforced by CI (`tests/test_privacy.py`, `tests/test_ranking.py`,
`tests/test_snapshot.py`).

## Development

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -e ".[dev]"
pytest        # privacy red lines + ranking + snapshot must be green
```

Set `OPENHIRE_DATABASE_URL=postgresql+psycopg://…` to run against Postgres instead of the
default local SQLite file (`~/.openhire/openhire.db`).

## Roadmap

- **v0.2 – v0.3 (shipped)** — CN ATS adapters (北森 Beisen + Moka) · weekly auto-refreshed
  public snapshot · `ghost_score` public beta · 139 employers across US / EU / China
- **next** — Employer claim + verified badges — employers can [reserve their claim
  today](https://github.com/gzchenhao/openhire/issues/new?template=employer_claim.yml) via a
  corporate-identity GitHub issue (zero-cost now; badges + listing-status control ship next) ·
  response-SLA enforcement (7-day auto-delist) · **redacted proof-of-fit** — an anonymous,
  candidate-authorized match summary that travels with an application (skills overlap only;
  identity never included, résumés still never transit the server)
- **v1.0** — Open, vendor-neutral schema extension for AI-readable job postings

## FAQ

**Where does the job data come from?**
Directly from 139 employers' own public ATS APIs (Greenhouse, Lever, Ashby, 北森 Beisen, Moka) — the
same endpoints that power their careers pages. No scraping, no third-party job boards. `source` is
always `ats_public_api`, and `verified_at` records the last time we confirmed each posting live.
The public index is auto-refreshed weekly, so a fresh `ohp bootstrap` starts from recent data.

**Why should I trust `ghost_score`?**
It's a pure, open, unpurchasable function — `min(1, 0.15·relist_count + staleness)` aged off the
**real** ATS posting date, not our crawl date. The formula lives in `pipeline/ghost_score.py`,
is unit-tested, and takes no money as input (red line #2). Long-open, repeatedly-relisted
postings score higher; you can always re-rank client-side. Read it as **signal-to-noise, not
bad faith**: plenty of high-scoring listings are legitimate evergreen talent pools. Employers
who want their listing activity represented accurately can claim their tenant (see Roadmap).

**Does my résumé actually go through the server — really?**
No. There is no résumé anywhere in the protocol. `authorize_application` has no résumé/file
parameter (it structurally cannot accept one), matching runs on your machine, and the only thing
that ever transits the server is a short anonymous fingerprint like `#a3f9`. This is enforced by
`tests/test_privacy.py`, and the published snapshot carries **zero** user data (`tests/test_snapshot.py`).

**Does it support China (中国区)?**
Yes — this is what sets OpenHire apart. Employers on **北森 Beisen** (`<tenant>.zhiye.com`) and
**Moka** (`app.mokahr.com`) are indexed: 20+ autonomous-driving / robotics / embodied-AI
companies including 宇树 Unitree, 小鹏 XPeng, 优必选 UBTECH, 梅卡曼德 Mech-Mind, 速腾聚创 RoboSense,
元戎启行 DeepRoute, 星海图 Galaxea, 傅利叶 Fourier, 普渡 Pudu. Pay published as 月薪 keeps its real
period (`salary_period`), so a salary floor no longer silently drops Chinese roles.

**飞书招聘 (Feishu Hire) is not supported and won't be**: it signs its job-list requests with a
ByteDance `_signature` and gates them behind a captcha SDK, so its listings are not publicly
readable. We don't break anti-bot measures.

**How do I get a company added?**
Open a **Company inclusion request** issue (title it with the company + its ATS URL) — this is
the best way to contribute. If you code, add it to `src/openhire/seed/candidates.py` (company
slug + ATS vendor/tenant) and open a PR; the seeder validates tenants against the live API.

## License

MIT © OpenHire Protocol · PRs welcome.

---

*Built by a deep-tech headhunter who does not write code, pair-programming with Claude Code. Full acceptance reports, including the mistakes, in [`reports/`](reports/).*
