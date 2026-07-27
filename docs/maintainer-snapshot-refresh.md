# Maintainer op card — weekly snapshot refresh

The public index snapshot is a **GitHub Release asset** (`openhire-index.db.gz`), not part of
the package. `ohp bootstrap` downloads it, so it must be refreshed so new users start from
recent data. **Cadence: once a week (manual).**

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

## Notes
- The snapshot is ~13 MB gzipped (~85 MB uncompressed). Well within a Release asset.
- If you rev the package version, cut a new Release tag and update `OPENHIRE_SNAPSHOT_URL` to
  point at that tag (or keep a stable `latest`-style tag for the asset).
- Never commit `dist/` or `*.db.gz` (already in `.gitignore`).
