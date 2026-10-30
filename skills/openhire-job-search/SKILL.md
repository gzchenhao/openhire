---
name: openhire-job-search
description: A local job-search workflow on top of the OpenHire MCP server. Use when the user wants to evaluate how a posting fits them, tailor their CV to a posting, build a STAR interview story bank, or draft a short outreach note. The CV and every personal detail stay in the user's own folder; OpenHire tools only ever receive a job_id or a company name.
---

# OpenHire job search (local workflow)

OpenHire supplies facts about postings from employers' own hiring systems: whether a posting is still live, how long it has been open, the degree and years it asks for, and whether the company is publishing more or fewer postings lately. Everything about the user stays on this machine. You (the assistant) do the reading and writing locally.

## The one rule that never bends

Never pass the CV, its text, the user's name, email, phone, address or any file to an OpenHire tool. Tools take only a `job_id`, a company name, search filters, or an anonymous fingerprint. If a step seems to need the CV on the server, it does not: do it here, on this machine.

## Files (in the folder the user is working in)

| File | What it is | Who writes it |
|---|---|---|
| `cv.md` | The user's real CV. Source of truth. | The user. You never invent anything in it. |
| `openhire/evaluations.md` | One section per posting evaluated. | You. |
| `openhire/cv-<job_id>.md` | A CV reworded for one posting. | You, from `cv.md` only. |
| `openhire/stories.md` | STAR + reflection stories mined from `cv.md` and what the user tells you. | You. |
| `openhire/outreach.md` | Short notes the user may send themselves. | You. The user sends them, never you. |

If `cv.md` does not exist, ask the user to put their CV there (Markdown or pasted text). Do not upload it anywhere to read it.

## Modes

### 1. Evaluate a posting ("评估这个岗位", "how well do I fit")

1. Get the facts: `search_jobs` (by company and title) to find the row, then read its `dates_in_words`, `check_before_apply`, `requirements` and `apply_channel`; `get_company_info` for `hiring_trend`; optionally `check_employer` with the `job_id`.
2. Compare with `cv.md` here: list which stated requirements the CV shows evidence for, which it does not, and what is only "preferred".
3. Write a section to `openhire/evaluations.md` with three parts: **Facts from the employer's system** (quote the sentences), **Fit against my CV** (met / not shown / preferred only), **Questions to ask before applying**.
4. Do not give a pass/fail verdict or a single score that says "do not apply". Never call a posting fake, a ghost or 僵尸岗: a long time open is a measured fact, not evidence. The user decides.

### 2. Tailor the CV to one posting ("按这个岗位改简历")

1. Read the posting's requirements and description (`read_board` with `ats_job_id` gives the full text for boards it reads; otherwise the row's excerpt).
2. From `cv.md` only, reorder and reword so the evidence the posting asks for comes first, using the posting's own terms where the CV truly supports them.
3. Reformulate, never fabricate: no new employers, titles, dates, numbers or skills. If the posting asks for something the CV does not show, leave it out and tell the user.
4. Write `openhire/cv-<job_id>.md`. Show the user what changed.

### 3. Story bank ("帮我准备面试故事")

From `cv.md` and what the user tells you, write STAR + Reflection stories (Situation, Task, Action, Result, what you would do differently) into `openhire/stories.md`, tagged with the requirements they answer. Only real events; ask when a number or detail is missing instead of guessing.

### 4. Outreach note ("帮我写打招呼")

Draft a note under 300 characters to a recruiter or hiring manager for one posting, in the user's language, built on one concrete match between the CV and the posting. Write it to `openhire/outreach.md`. You never send it, never open any platform, never log in.

### Follow-up

After the user says they applied, record the postings with `check_applications` (`add_job_ids`, the user's fingerprint) and, later, report which have closed so they can stop waiting.
