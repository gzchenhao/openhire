# employers/

Self-reported rosters: one `<slug>.json` per employer whose own system we cannot read
(Feishu Recruitment, platform-only, a careers page with no job list), written by the
maintainer from the employer's spreadsheet after verifying the corporate identity behind
it. The adapter is `src/openhire/ats/self_reported.py`, the employer is declared in its
`SELF_REPORTED_EMPLOYERS`, and the four conditions that keep this from being a job board
are in that module's docstring: verified identity, rows marked `employer_self_reported`
with `date_signal: self_reported`, 90-day expiry per renewal, nothing about ranking.

How an employer gets here: https://gzchenhao.github.io/openhire/employers.html
Tool: `scripts/import_employer_roster.py`.
