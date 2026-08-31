# Maintainer op card — weekly snapshot refresh

The public index snapshot is a **GitHub Release asset** (`openhire-index.db.gz`), not part of
the package. `ohp bootstrap` downloads it, so it must be refreshed so new users start from
recent data.

**Cadence: once a week, automatically.** `.github/workflows/refresh-snapshot.yml` runs every
Monday 06:10 UTC (and on demand via Actions → *Refresh index snapshot* → Run workflow). It
downloads the published snapshot, re-seeds the roster, re-crawls every public board with the
**free heuristic** extractor, rebuilds, and re-uploads the asset under the same filename. It
holds **no secrets** — only GitHub's automatic per-run token, scoped `contents: write` — so
there is nothing to rotate and nothing that can expire. A failed run emails the repo owner
through GitHub's default notification; `ohp ingest --all --fail-over 10` makes a crawl that
loses more than 10 boards exit non-zero rather than publish a gutted index quietly.

The manual steps below remain the fallback (CI down, or an urgent refresh) — and are still
the ONLY way to publish LLM-extracted skills, which is a local-only pass (see *What CI cannot
do* at the bottom).

The snapshot contains ONLY `companies` + `jobs`. `ohp snapshot-build` refuses to build if any
user-state (watches/applications) would leak in — you cannot accidentally publish user data.

## Steps (≈5 min)

Run from the repo root, in the project venv (`.venv\Scripts\activate`).

```powershell
# 1. Refresh your local index from the live public ATS (free; heuristic is fine).
#    (Skip if your local ~/.openhire/openhire.db is already current.)
#    IMPORTANT: force the heuristic. OPENHIRE_EXTRACTOR defaults to "auto", which picks
#    DeepSeek whenever DEEPSEEK_API_KEY is set (.env) — i.e. a paid re-extraction of every
#    changed JD. The snapshot does not need it.
$env:OPENHIRE_EXTRACTOR = "heuristic"
ohp ingest            # one-shot; `--daemon` is the looping variant

# 2. Build the snapshot (writes dist/openhire-index.db.gz; validates zero user-state).
ohp snapshot-build --out dist/openhire-index.db.gz

# 3. Confirm the summary: "公司 96 · 职位 ~14k" and "零用户态校验通过".
#    If it errors ERR_SNAPSHOT_REDLINE, STOP — user data leaked; do not upload.
```

## Upload to the Release

One command replaces the old drag-and-drop; `--clobber` overwrites in place, so the
**filename stays identical** (the bootstrap URL is fixed):

```powershell
gh release upload v0.1.0 dist/openhire-index.db.gz --clobber --repo gzchenhao/openhire
```

Then verify:

1. `gh release view v0.1.0 --repo gzchenhao/openhire --json assets` → `updatedAt` is today.
2. `curl -sIL <SNAPSHOT_URL>` (the URL in `src/openhire/config.py`) → `HTTP 200` and a
   `Last-Modified` of today.
3. Sanity-check as a user would: in a throwaway dir, `OPENHIRE_DATABASE_URL=…/tmp.db ohp bootstrap`
   and confirm it downloads + reports a low "龄 N 天".

## What CI cannot do (why the manual pass still exists)

- **LLM extraction.** CI is deliberately key-free, so it runs the heuristic extractor. Jobs
  whose JD changed since the last snapshot come back with heuristic skills until the next
  local pass. Run the enrichment on your own machine, where the key lives in `.env`:

  ```powershell
  ohp extract-rebuild --backend glm     # skills for every job no LLM has touched (CNY 0, coding plan)
  ohp extract-role-family --backend glm # role_family for the NULL rows
  ```

  Then build + upload the snapshot with the steps above, so the enriched data reaches users.
  Roughly monthly is enough; CI keeps freshness up in between.
- **Chinese (Beisen) boards, if the runner cannot reach them.** GitHub runners sit outside
  China. The workflow probes `<tenant>.zhiye.com` on every run and prints the HTTP status —
  read that step's log for the current answer. An unreachable board is NOT destructive: the
  crawl records a failure and the existing jobs stay in the index, ageing out naturally via
  `ghost_score`. If CN stays unreachable from CI, refresh those tenants locally with
  `ohp ingest -c unitree -c galaxea …`.

## Notes
- The snapshot is ~13 MB gzipped (~85 MB uncompressed). Well within a Release asset.
- If you rev the package version, cut a new Release tag and update `OPENHIRE_SNAPSHOT_URL` to
  point at that tag (or keep a stable `latest`-style tag for the asset).
- Never commit `dist/` or `*.db.gz` (already in `.gitignore`).
