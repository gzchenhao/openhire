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

## Maintainer checklist for one employer (reports/064)

1. The sheet arrives from a corporate mailbox. Note the sender's domain; a look-alike
   domain fails the first check and nothing else runs.
2. `python scripts/verify_employer.py --xlsx <sheet> --sender-domain <domain>` runs the
   automatic checks (统一社会信用代码 check digit, sender domain, ICP number on the homepage,
   domain age via RDAP, earliest Wayback capture, public phone on the company's own page,
   footprint links) and prints the three things only a human can do.
3. Do them: the 工商 record on gsxt.gov.cn, the ICP record on beian.miit.gov.cn, and the
   callback to the number on the company's own site (never the number in the email).
   Judge the industry footprint yourself.
4. `python scripts/import_employer_roster.py ... --verification "<the sentence the
   verifier printed, completed with what you did>"`; rows that match the scam red flags
   or publish an address off the company's domain are dropped by the script.
5. Declare the employer in `SELF_REPORTED_EMPLOYERS` with the same `verification`
   sentence, commit both, and the Monday snapshot carries it. Tests refuse an entry with
   an empty `verification`.
6. One report against a roster: delist first (remove the entry and the file), ask later.
