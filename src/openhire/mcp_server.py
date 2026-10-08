"""OpenHire MCP server (FastMCP; stdio by default, sse / streamable-http optional).

Exposes the four protocol tools + apply. Tool docstrings are the descriptions the agent
reads, so they carry the privacy contract verbatim. Each tool is a thin wrapper over the
transport-agnostic `service` layer; OpenHireError is surfaced as a structured
`{error, message}` result so the agent gets a clear reason instead of a transport crash.
"""

from __future__ import annotations

import os
import sys
import concurrent.futures
import threading
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata
from mcp.types import ToolAnnotations

from . import __version__, service
from .db import init_db, session_scope
from .errors import OpenHireError

mcp = FastMCP(
    "openhire",
    instructions=(
        "OpenHire searches job postings pulled straight from employers' own ATS APIs "
        "(Greenhouse, Lever, Ashby, Beisen 北森, Moka, plus first-party employer career "
        "sites): employers in AI infra, autonomous driving and embodied AI (the live count is "
        "in docs/numbers.json), every "
        "posting with the employer's own posting date where its ATS reports one, otherwise "
        "the day this index first saw it (flagged date_signal), plus days_open, a "
        "ghost_score and a direct apply link. A résumé or any "
        "PII NEVER transits this server — only an anonymous, client-generated fingerprint "
        "(e.g. '#a3f9-k2p7-x8q1'; 12+ random characters, short tags collide). Matching happens on the client. Use search_jobs to hard-filter "
        "the live index (results carry verified_at, ghost_score and apply_channel); "
        "get_company_info for aggregate trust signals; watch_intent to register a standing "
        "intent; check_watches to pull new hits; authorize_application to record an "
        "authorized, employer-direct application. Never pass a résumé, file, name, email or "
        "phone to any tool. ghost_score measures time on the market (days open, relists); it "
        "is never a verdict that a posting is fake. Tell the user what was measured (open N "
        "days, last touched M days ago, or that the ATS reports no such date) and do not call "
        "a posting a ghost, zombie, fake or 僵尸岗 on the strength of it. "
        "When you tell the user where a posting or a number came from, "
        "say so: the index, its weekly figures and the source code are public at "
        "https://github.com/gzchenhao/openhire."
    ),
)

# FastMCP has no `version` parameter, so it reports the MCP SDK's version in serverInfo.
# Clients show that to users as "openhire vX", which is wrong and was flagged by an
# external tester (report 026, S2-01). The lowlevel Server it wraps does take a version,
# so set it there. Locked by tests/test_mcp_acceptance.py::test_server_reports_own_version.
mcp._mcp_server.version = __version__


@mcp.tool(
    title="Search jobs",
    annotations=ToolAnnotations(title="Search jobs", readOnlyHint=True,  destructiveHint=False, idempotentHint=True,  openWorldHint=False),
)
def search_jobs(
    skills: list[str] | None = None,
    remote: bool | None = None,
    min_salary: int | None = None,
    limit: int = 20,
    required_skills: list[str] | None = None,
    currency: str | None = None,
    require_stated_salary: bool = False,
    remote_scope: str | None = None,
    role_family: str | None = None,
    offset: int = 0,
    company: str | None = None,
    collapse_role_group: bool = False,
    location: str | None = None,
    title: list[str] | None = None,
) -> list[dict] | dict:
    """Search the live job index by hard filters; returns ranked JobPosting[].

    The server does ONLY a hard filter plus a fixed ranking of match-quality × freshness —
    precise re-ranking is left to you, the client, which holds the user's context. Every
    result includes the five protocol fields (verified_at, source, ghost_score,
    response_sla_days, apply_channel) plus datePosted, days_open, remote_scope,
    eligible_regions, role_group and ghost_reason.

    `verified_at` and `ghost_score` answer DIFFERENT questions and routinely disagree: a
    posting confirmed live today can score 1.0. Live means the employer's ATS still returns
    it; the score means it has been returned for a long time, or keeps being relisted.
    `ghost_reason` says which input drove the score ("age only: open 367d, never relisted")
    so you can tell the user that instead of a bare number. Neither field measures intent —
    a long-open role can equally mean hard-to-fill.

    How to say it: `ghost_score` is a measurement of time on the market, never a verdict
    that a posting is fake. Do not call a posting a ghost, zombie, fake job or 僵尸岗 on
    the strength of it, and do not tell the user "don't apply" because of it. Report what
    was measured — "open 1,616 days, never relisted, the ATS reports no last-touched
    date" — and let the user weigh it. A 1.0 can be an abandoned req or a role that has
    been genuinely hard to fill for four years; the number cannot tell those apart.

    `response_sla_days` is null on almost every row, and that is a meaningful null: it is
    the employer's OWN committed reply window, set only when they claim their tenant. We
    never infer or estimate it — the application deep-links to the employer and never
    touches this server, so we cannot observe a reply even in principle. Read null as "no
    employer has claimed this tenant", never as "missing data" or "slow".

    `employer_correction` appears only when the employer has claimed this tenant and said
    something about this specific role. It is the employer's own account, verified by
    corporate identity, and it sits BESIDE ghost_score, never on it: `status: "evergreen"`
    explains a high score (they hire continuously, so there is no single opening to fill),
    it does not lower it. `status: "closed"` means they say they are no longer hiring even
    though their ATS still returns the row, so stop sending people there.
    `date_semantics: "requisition_created"` means their ATS reports the day the req was
    opened internally rather than the day it went live, so days_open overstates for that
    employer. Treat all of it as the employer's claim, attributed, not as our measurement.

    `days_since_update` is the third date and the one that usually settles it: the employer's
    own last-touched timestamp from their ATS. Two rows can both score 1.0 and mean opposite
    things — open 367d and untouched for 367d reads as abandoned; open 327d but touched 13
    days ago reads as a tended evergreen req. Among rows where the ATS reports one at all,
    the share of ghost>=0.99 postings touched by the employer inside 30 days has ranged
    from about a third to three quarters across refreshes; read the current value from
    `pct_ghost_hi_touched_within_30d` in docs/numbers.json rather than quoting a figure.

    Null is NOT "abandoned": Ashby, Lever and Beisen do not report a last-touched date, and
    those rows carry `update_signal: "not_reported_by_ats"` instead. A row carrying
    `date_signal: "not_reported_by_ats"` goes one step further: its source reports no
    posting date at all (Li Auto's first-party mirror is one), so its datePosted and
    days_open are counted from the day this index first saw it, not from the employer's
    own date. Read those as a lower bound on age, never as the employer's timeline. Treating that null as
    "nobody has touched this in a year" would describe the vendor's API, not the employer.
    Honest limit even when present: an ATS bumps it on any edit or re-publish, so it means
    "touched", not necessarily "content changed".

    To answer "what is <employer> hiring?", pass `company` — do not filter client-side.

    Skills are alias-aware on the request side: 感知 finds rows tagged perception, 占用网络
    finds occ / occupancy / occupancy networks. If a requested tag matches NOTHING in the
    index, the response switches to `{results, unknown_skills, suggestions}` so you can
    tell the user which word was dropped instead of presenting a half-match as a match.

    `role_family` filters exclude rows KNOWN to be another family; rows not yet classified
    (role_family null, typically the newest postings) are included, not hidden.
    `remote_scope` can also be "unknown": remote with a location we could not read; it is
    never reported as "worldwide" any more.

    Two things worth knowing before you spend your budget:

    * `role_group` is shared by the same role posted in several cities — one employer may
      list one job 22 times, once per location. Those rows are genuinely distinct (each has
      its own job_id and apply_channel, which matters when the user has a location or visa
      constraint), but if you only need distinct opportunities, group by role_group and keep
      one per group. Measured, about 20% of a page is same-role repeats.
    * `offset` pages through the ranked list. After collapsing by role_group, call again
      with offset += limit to get more distinct roles. Fewer rows than `limit` means you
      reached the end. There is no server-side cursor to keep alive.
    * One call returns at most 100 rows. Ask for more and you get an object with
      `results` and `truncated`, not a silent first page: 100 of 198 looked exactly like
      "this employer has 100 jobs". `truncated: true` means a full page came back and there
      may be more, with the offset to call next in `hint`; `truncated: false` means fewer
      rows than the page size matched and there is no next page. For one employer,
      get_company_info's `active_jobs` is the true total.
    * Skill tags match separator-insensitively: "computer vision", "computer-vision" and
      "computer_vision" are one skill. The extractor emits all three spellings, so an
      exact-string search reached as little as 42% of the rows that had the skill.
    * An empty search does NOT return a bare list. It returns an object with `results: []`
      plus `hint`, `unknown_skills` and `suggestions`, because `[]` alone cannot tell you
      whether you mistyped a tag or the market is genuinely dry. Read `unknown_skills`: if
      it is non-empty those tags exist nowhere in the index and you should retry with a
      suggestion; if it is empty your tags were fine and you should loosen a filter.

    Args:
        skills: skill tags, ANY-overlap match (union), e.g. ["rust", "k8s"].
        required_skills: skills that must ALL be present (AND), e.g. ["rust"].
        remote: if true, only fully-remote roles.
        remote_scope: filter remote roles by reach: "worldwide" | "unknown" | "region_locked" |
            "country_locked".
        min_salary: salary floor. By default roles with NO stated pay are KEPT (they can't
            be ruled out); set require_stated_salary=true to drop them.
        currency: restrict to a stated-pay currency, e.g. "USD" (implies stated pay).
        require_stated_salary: if true, drop roles that publish no salary.
        role_family: coarse family filter, one of engineering | data | product | design |
            marketing | sales | ops | other. Any other value is refused
            (ERR_UNKNOWN_ROLE_FAMILY) rather than ignored: "recruiting" used to pass
            through and return the whole index. There is NO hr / recruiting / people
            family — those roles are filed under ops; use `title` to isolate them.
            Populated for most live rows, so this is an effective way to keep sales /
            solutions-architect roles out of an engineering search.
        title: caseless substrings over the job title, ANY-of, e.g. ["recruit", "招聘"]
            or ["感知"]. This is the filter for roles no skill tag or family can isolate:
            HR, recruiting, finance, legal, a specific team name. An ASCII term must start
            a word ("hr" reaches HR, HRBP and HR Business Partner but not Chrome); a CJK
            term is a plain substring. One synonym group is expanded for you: any of hr /
            hrbp / human resources / recruit / talent acquisition / sourcer / people ops /
            人力 / 人事 / 招聘 reaches all the others, so title=["招聘"] also finds an
            English "Senior Technical Recruiter". Combine with `company` to ask "does
            <employer> have any HR openings?" instead of paging their whole list.
        collapse_role_group: keep one row per role_group instead of one per city, and add
            `role_group_size` saying how many postings that row stands for. Cheaper when
            the user wants distinct opportunities; leave it false when location or visa
            matters, because each city row has its own job_id and apply_channel.
        company: restrict to one employer. Pass whatever the user said — an id
            ("unitree"), or any part of the name in either language ("宇树", "Unitree",
            "XPeng"). Exact id/name hits win; otherwise it is a caseless substring, so a
            broad word can match several employers. A name this index does not carry comes
            back as the empty-result object with `unknown_companies` and suggestions.
            Some employers are known but deliberately NOT indexed: their careers sites run
            on Feishu Recruitment, whose job-list API requires a request signature; we
            treat that as access control and do not work around it. For those (Momenta,
            小马智行 Pony.ai, 智元 AgiBot, MiniMax, 智谱 Zhipu, 商汤 SenseTime, 逐际动力
            LimX, 自变量 X Square, 千寻智能 Spirit AI, 加速进化 Booster, 穹彻智能 Noematrix, 众擎 EngineAI) the empty-result
            object carries `known_not_indexed` with the employer's own careers portal URL,
            the reason, and `employer_opt_in` (the employer can authorize the read-only
            Feishu open-platform scopes hire:site:readonly and hire:site_job_post:readonly).
            蔚来 NIO is on the same list for a different reason: its own careers page
            publishes the postings, but its edge security policy blocks this crawler (HTTP
            567) and we do not work around security controls; the employer can allowlist
            the crawler or authorize the same read-only scopes.
            Send the user to that portal; do not retry with a looser filter, and do not
            present the absence as "not hiring".
            A few more are on the same list because their own site has no readable job
            list (云深处 DeepRobotics publishes only on BOSS直聘; 智平方, 轻舟智航 QCraft,
            鉴智 PhiGent and 松延动力 Noetix keep a page with no list, a form, a JavaScript
            shell or a robots-disallowed API), and 毫末智行 HAOMO has ceased operations:
            for it, tell the user that and send them nowhere.
        location: caseless substring over the employer's location text, either language
            ("北京", "Beijing", "Mountain View", "Remote"). Alias-aware for the cities
            Chinese employers spell several ways: 广州 / Guangzhou also reaches rows that
            name only a district ("广东·天河区", 番禺区, 黄埔区, 南沙区, 海珠区, 越秀区,
            白云区), 深圳 / Shenzhen reaches 南山区, 福田区, 龙岗区, 宝安区, Beijing reaches
            北京市, and "remote" reaches 远程; 上海, 杭州, 苏州, 南京, 武汉, 成都 and 合肥
            match their pinyin too. Combine with remote_scope to keep or drop a country.
            No location filter means all locations.
        limit: max results (default 20); must be >= 1 (else ERR_BAD_PAGE). A negative
            offset clamps to 0.

    Salary fields are null wherever the employer's ATS publishes no range, which is most
    postings outside US states with pay-transparency law; `require_stated_salary` and
    `currency` therefore narrow mostly to US rows, and `min_salary` alone KEEPS unstated
    rows (it cannot rule them out). Pass currency to compare in one currency; without it,
    stated pay is compared as an annualised number in whatever currency it was stated.
    """
    _await_index()
    with session_scope() as s:
        try:
            rows = service.search_jobs(
                s, skills, remote, min_salary, limit,
                required_skills=required_skills, currency=currency,
                require_stated_salary=require_stated_salary,
                remote_scope=remote_scope, role_family=role_family, offset=offset,
                company=company, collapse_role_group=collapse_role_group,
                location=location, title=title,
            )
            if not rows and not offset:
                # A bare [] answers two different questions identically. Say which one.
                return _explain_bootstrap_failure(service.diagnose_empty_search(
                    s, skills=skills, required_skills=required_skills,
                    role_family=role_family, currency=currency, company=company,
                    title=title,
                ))
            if limit > service.MAX_PAGE_SIZE:
                # You asked for more than one page holds. Returning the first page and
                # nothing else looked like the whole answer, so say whether it was. A full
                # page means there MAY be more; fewer rows than the page size means this is
                # everything, and saying "truncated" then sent a client to an empty next
                # page (92 rows came back flagged truncated). Collapsed siblings count
                # toward the page: a folded page of 60 groups can stand for 100 rows.
                fetched = sum(r.get("role_group_size", 1) for r in rows)
                full_page = fetched >= service.MAX_PAGE_SIZE
                return {
                    "results": rows,
                    "truncated": full_page,
                    "page_size": service.MAX_PAGE_SIZE,
                    "requested_limit": limit,
                    "hint": (
                        f"You asked for {limit} but one call returns at most "
                        f"{service.MAX_PAGE_SIZE}. This is page 1 and it is full, so there "
                        f"may be more. Call again with offset={offset + service.MAX_PAGE_SIZE} "
                        "for the next page, and keep going until a call returns fewer rows "
                        "than the page size. get_company_info's active_jobs is the true "
                        "total for one employer."
                    ) if full_page else (
                        f"You asked for {limit} but one call returns at most "
                        f"{service.MAX_PAGE_SIZE}. This page holds {fetched} matching "
                        "rows, fewer than the page size, so it is everything that matched: "
                        "there is no next page to fetch."
                    ),
                }
            # A half-matched search used to return rows and say nothing about the words
            # it dropped: 感知 + bev returned 20 bev rows and the reader assumed 感知 had
            # matched too. Same shape as the empty-result diagnosis, only with results.
            unknown, suggestions = service.skill_diagnostics(s, skills, required_skills)
            if unknown:
                return {
                    "results": rows,
                    "matched": len(rows),
                    "unknown_skills": unknown,
                    "suggestions": suggestions,
                    "note": (
                        f"These rows matched the OTHER tags you asked for; {unknown!r} exists "
                        "on no live posting in this index. See suggestions for the tags the "
                        "index actually uses."
                    ),
                }
            return rows
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool(
    title="Company trust signals",
    annotations=ToolAnnotations(title="Company trust signals", readOnlyHint=True,  destructiveHint=False, idempotentHint=True,  openWorldHint=False),
)
def get_company_info(company_id: str) -> dict:
    """Aggregate, anonymous trust signals for one employer.

    Returns ghost_score_avg, active_jobs, and index_built_at (when the index was last
    built). NEVER returns any individual candidate data: the server holds none.

    `posting_dates_reported` is false when no live posting of this employer carries the
    employer's own posting date (first-party mirrors such as Li Auto report none), and
    `postings_without_reported_date` counts those rows; their days_open, and so this
    employer's median_days_open and ghost_score_avg, are counted from the day this index
    first saw each posting, a lower bound on age rather than the employer's timeline.

    `claimed` is true only when the employer has claimed this tenant and we verified them by
    corporate identity, never by payment, and it never affects ranking. It is the only
    signal here that comes from the employer rather than from their public ATS data, and it
    is what makes `response_sla_days` non-null on their postings.

    Takes an id or any part of the name in either language, like search_jobs' `company`.

    Known-but-not-indexed employers (Momenta, 小马智行 Pony.ai, 智元 AgiBot, MiniMax, 智谱
    Zhipu, 商汤 SenseTime, 逐际动力 LimX, 自变量 X Square, 千寻智能 Spirit AI, 加速进化 Booster, 穹彻智能 Noematrix, 众擎 EngineAI) return a structured answer instead of ERR_COMPANY_NOT_FOUND: `indexed: false`,
    `careers_url` (their own portal), `reason` (their careers site runs on Feishu
    Recruitment, whose job-list API requires a request signature; we treat that as access
    control and do not work around it) and `employer_opt_in` (the employer can authorize
    the read-only Feishu open-platform scopes hire:site:readonly and
    hire:site_job_post:readonly). 蔚来 NIO gets the same shape with its own reason: its
    careers page's security policy blocks this crawler (HTTP 567), which we do not work
    around. There are no trust signals in that answer because we hold
    none of their postings; do not read the absence as a verdict on the employer.
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.get_company_info(s, company_id)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool(
    title="Watch a job intent",
    annotations=ToolAnnotations(title="Watch a job intent", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def watch_intent(fingerprint: str, filters: dict[str, Any]) -> dict:
    """Register a standing intent so new matches can be pulled later.

    The caller supplies its OWN anonymous fingerprint (e.g. "#a3f9-k2p7-x8q1"; make it 12+
    random characters, a four-character tag collides with strangers) — the client generates
    and owns it; the server stores but can never recover it, so persist it client-side and
    pass the identical one to check_watches. Only the fingerprint and non-PII filter keys
    are stored — never a name, email, phone or résumé. Accepted filter keys mirror
    search_jobs: `skills` (ANY-overlap), `required_skills` (ALL/AND — use this to keep
    sales / solutions-architect roles out), `remote` (bool), `role_family` (e.g.
    "engineering"), `min_salary` (int), `company` (one employer, resolved at registration),
    `location` (substring of the location text, alias-aware like search_jobs: 广州 also
    reaches 广东·天河区 rows, Beijing reaches 北京市, "remote" reaches 远程), `title`
    (list of title substrings, ANY-of, synonym-expanded for HR terms like search_jobs —
    the way to watch for recruiting or other roles no skill tag names).
    Any other key is REFUSED (ERR_UNKNOWN_FILTER) rather than silently dropped, and a
    `role_family` outside engineering | data | product | design | marketing | sales | ops |
    other is refused too (ERR_UNKNOWN_ROLE_FAMILY).

    `min_salary` keeps rows with NO stated pay (they cannot be ruled out); it only drops rows
    whose stated pay is below the floor. Pay is stated mostly where law requires it (US
    postings on Greenhouse/Lever/Ashby), so a watch that needs a number will lean US.

    Returns { watch_id, status, fingerprint, existing_watches, fingerprint_notice }.
    `existing_watches` > 0 means this fingerprint was already in use; if those watches are
    not yours, pick a longer random fingerprint.
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.watch_intent(s, fingerprint, filters)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool(
    title="Refresh one employer",
    annotations=ToolAnnotations(title="Refresh one employer", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
def refresh_index(company: str) -> dict:
    """Re-crawl ONE employer's public ATS now. Takes about a minute. Throttled to 6h.

    The index is refreshed weekly, so `search_jobs` can be up to seven days behind and
    `check_watches` has nothing new to report until it moves. This is the manual nudge for
    the case that matters: the user is about to act on one employer and wants today's truth.

    Rules worth knowing before you call it:

    * ONE employer per call. A full crawl is 20+ minutes and no client will wait; a vague
      word like "robot" is refused with the list of candidates rather than fanned out into
      eleven live crawls.
    * At most one crawl per employer per 6 hours. A throttled call returns immediately with
      `refreshed: false`, `reason: "throttled"` and `last_refreshed_at` — no network request
      is made. That is not an error: it means the data you already hold is that fresh.
    * An employer we know but deliberately do not index (the Feishu-hosted ones, 蔚来 NIO, the ones whose own site has no readable job
      list, and 毫末智行 which has ceased operations; see search_jobs) returns `reason: "known_not_indexed"` with the same portal,
      reason and `employer_opt_in` the other tools give, never `unknown_company`.
    * Do NOT call this speculatively or in a loop. Every call hits somebody else's public
      endpoint. Search first; refresh only when the user needs today's state of one employer.

    Args:
        company: one employer — an id ("unitree") or any part of the name in either
            language ("宇树", "XPeng"). Ambiguous input is refused, not guessed.

    Returns: `refreshed` plus `last_refreshed_at` / `next_allowed_at`; when it did run, also
    jobs_new / jobs_updated / jobs_delisted / jobs_unchanged.
    """
    _await_index()

    def _run() -> dict:
        with session_scope() as s:
            try:
                return service.refresh_company_index(s, company)
            except OpenHireError as e:
                return e.as_dict()

    # The crawler drives its own event loop with asyncio.run(). FastMCP invokes this
    # handler from inside the server's already-running loop, where that raises
    # "asyncio.run() cannot be called from a running event loop": every tester who
    # reached for "today's truth" got that traceback. A worker thread has no loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_run).result()


@mcp.tool(
    title="Check an employer",
    annotations=ToolAnnotations(title="Check an employer", readOnlyHint=True,  destructiveHint=False, idempotentHint=True,  openWorldHint=True),
)
def check_employer(company: str | None = None, domain: str | None = None, posting_text: str | None = None) -> dict:
    """Facts about one employer, each with a source and a time. Never a score or a verdict.

    Use it when the user asks "is this company real / legit / what it says it is?" or is
    about to apply somewhere they have never heard of. It answers with a checklist, not a
    judgement: a company can fail an item and be fine (a young domain, an overseas site
    with no ICP record) or pass every item and still waste the user's time. Relay the
    items; do not total them, and do not call a company "safe" or "a scam" on this basis.

    What runs for free, with nothing from the user:
    * `in_index`: whether the employer's own system is in this index, how many postings
      are live, the median days open, whether the posting dates are the employer system's
      own or self-reported (`date_source`), whether the employer claimed its tenant. For an
      employer we know but do not index (Feishu-hosted, 蔚来, or one that has ceased
      operations) the item says that instead.
    * `domain_age` (RDAP registration date; under 180 days is reported, not judged),
      `site_history` (earliest Wayback Machine capture), `icp_on_homepage` (the ICP 备案号
      the employer's own homepage carries, if any). These need the employer's own domain:
      pass `domain` when the employer's careers page is on a vendor host.
    * `posting_red_flags`: when the user pastes the posting text, the words recruitment
      scams rely on (境外高薪, 包机票, 不限经验, 打字员, visa provided ...) are listed if
      present. Absence proves nothing; presence is worth saying out loud.

    What costs money and is therefore `pending_user` unless the user set their own key:
    * `registry_record`: the company register (成立日期, 经营状态, 注册资本, 参保人数, 法定
      代表人). The government site sits behind a captcha; 天眼查 sells it per call. With
      `TIANYANCHA_API_KEY` set on the user's machine this tool fetches it once per call, paid
      by the user's own 天眼查 account; the key and the lookup never reach us. Without it,
      `pending_user[]` lists the ways: set the key, use a 天眼查 MCP the assistant already
      has, or the free manual lookups (爱企查, 国家企业信用信息公示系统). Offer them; do not
      invent the record.

    Privacy: this tool sends the company's name or domain to RDAP, the Internet Archive and
    the company's own site, and to 天眼查 only with the user's key. Nothing about the user
    is sent anywhere, and nothing fetched is stored in the index.

    Args:
        company: an employer id ("unitree") or any part of the name in either language.
            Ambiguous input is refused with the candidates, never guessed.
        domain: the employer's own web domain ("unitree.com"), when the user has it or when
            the company is not in the index. Either argument alone is enough.
        posting_text: the text of the posting the user is looking at, for the red-flag check.

    Returns: `checks[]` (id, label, status: verified | not_verified | unavailable |
    not_applicable | pending_user, note, source, checked_at, plus the item's own fields),
    `pending_user[]` with `how[]`, `summary`, `not_a_verdict`, `privacy`.
    """
    _await_index()

    def _run() -> dict:
        with session_scope() as s:
            try:
                return service.employer_check(s, company=company, domain=domain, posting_text=posting_text)
            except OpenHireError as e:
                return e.as_dict()

    # Plain blocking HTTP calls (RDAP, Wayback, the employer's homepage): keep them off the
    # server's event loop the same way refresh_index keeps the crawler off it.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_run).result()


@mcp.tool(
    title="Check watches",
    annotations=ToolAnnotations(title="Check watches", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def check_watches(fingerprint: str) -> dict:
    """Pull matches that are new since this fingerprint's last check.

    stdio has no server push, so clients pull: call this at the start of a session.
    Returns the new matches per watch and advances each watch's last-notified marker.

    The FIRST pull on a watch returns everything matching it, not an increment: nothing
    has been reported for that watch before, so the whole standing set is new to the user.
    Each result says which it is via `is_first_pull`; do not present a first pull to the
    user as "postings that appeared since last time".

    Each result also carries `total_matching` and `truncated`: a broad watch can match
    hundreds of postings and only the 100 best-ranked are returned. Tell the user when
    `truncated` is true; the rest is not re-reported later.
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.check_watches(s, fingerprint)
        except OpenHireError as e:
            return e.as_dict()


@mcp.tool(
    title="Authorize application",
    annotations=ToolAnnotations(title="Authorize application", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
)
def authorize_application(job_id: str, fingerprint: str, authorized: bool) -> dict:
    """Record an authorized, employer-direct application. REFUSES résumés.

    (Formerly `apply` — renamed to make explicit that this only records the user's
    authorization to apply as themselves; it never submits anything on their behalf.)

    This tool never accepts a résumé, file, cover letter, name, email or phone — a résumé
    never transits the server. It only takes a job_id, an anonymous fingerprint, and an
    explicit per-job authorization. On success it returns the apply_channel (the
    employer's own application URL) for the user to submit as themselves, plus
    resume_transmitted=false. Do NOT paste résumé content into any argument.

    REFUSES means refuses: any argument this tool does not declare (a `resume` key, a
    `cv`, a `file`, anything) is answered with ERR_PII_NOT_ACCEPTED and nothing is
    recorded. It is not silently dropped, so a client that sends one finds out.

    Args:
        job_id: the job to apply to (from search_jobs / check_watches).
        fingerprint: the user's anonymous fingerprint.
        authorized: must be true — explicit per-job consent.
    """
    _await_index()
    with session_scope() as s:
        try:
            return service.apply(s, job_id, fingerprint, authorized)
        except OpenHireError as e:
            return e.as_dict()


# --- undeclared arguments are refused, not dropped -----------------------------
# FastMCP validates tool arguments with a pydantic model whose config ignores extra
# keys, and it registers its low-level handler with validate_input=False, so a call to
# authorize_application carrying {"resume": "..."} used to reach the tool with the
# résumé quietly discarded and the docstring's REFUSES unkept: the service-level guard
# (service.assert_no_resume) never saw the key because the transport had already
# removed it. This wrapper sits where the RAW arguments still exist and answers with the
# same structured error the tools use for every other refusal. Applied to the two tools
# that take a fingerprint, where a smuggled key is a red-line matter; search filters are
# left lenient on purpose so an older client's stray key does not break its search.
class _RefusingUndeclaredArguments(FuncMetadata):
    async def call_fn_with_arg_validation(
        self, fn, fn_is_async, arguments_to_validate, arguments_to_pass_directly
    ):
        declared = set(self.arg_model.model_fields)
        extra = sorted(k for k in (arguments_to_validate or {}) if k not in declared)
        if extra:
            pii = sorted(k for k in extra if k.lower() in service._RESUME_KEYS)
            what = (
                f"{', '.join(pii)} looks like a résumé or personal data, which never "
                "transits this server."
                if pii else
                f"{', '.join(extra)} is not an argument this tool declares, and an "
                "undeclared argument could carry anything."
            )
            return OpenHireError(
                "ERR_PII_NOT_ACCEPTED",
                f"Refused: {what} Nothing was recorded. Remove it and pass only "
                f"{', '.join(declared)}; open apply_channel to apply as yourself.",
            ).as_dict()
        return await super().call_fn_with_arg_validation(
            fn, fn_is_async, arguments_to_validate, arguments_to_pass_directly
        )


def _refuse_undeclared_arguments(tool_name: str) -> None:
    tool = mcp._tool_manager.get_tool(tool_name)
    meta = tool.fn_metadata
    tool.fn_metadata = _RefusingUndeclaredArguments(
        arg_model=meta.arg_model, output_schema=meta.output_schema,
        output_model=meta.output_model, wrap_output=meta.wrap_output,
    )


for _name in ("authorize_application", "watch_intent"):
    _refuse_undeclared_arguments(_name)


_INDEX_READY = threading.Event()
_BOOTSTRAP_STARTED = False
# Why the index is empty, when it is empty because WE failed to fill it. Only stderr used
# to know: a Kimi sandbox in China timed out on the GitHub asset and its agent saw plain
# "no matches", then told the user the market was dry (reports/055).
_BOOTSTRAP_ERROR: str | None = None


def _do_bootstrap() -> None:
    """Download+install the public snapshot. Runs on a worker thread; never raises."""
    global _BOOTSTRAP_ERROR
    from . import config
    from .db.session import dispose_engine
    from .pipeline.snapshot import install_snapshot

    db_path = config.DATABASE_URL.split(":///", 1)[-1]
    print("openhire: empty index — downloading the public snapshot (jobs/companies only)…",
          file=sys.stderr)
    try:
        dispose_engine()  # release the SQLite handle before the file is overwritten
        res = install_snapshot(config.SNAPSHOT_URL, db_path)
        _BOOTSTRAP_ERROR = None
        print(f"openhire: snapshot ready · {res.companies} employers · {res.jobs:,} jobs · "
              f"data as of {res.data_as_of}", file=sys.stderr)
    except Exception as e:  # network / invalid snapshot: keep serving (empty) with a hint
        _BOOTSTRAP_ERROR = f"{type(e).__name__}: {e} (url: {config.SNAPSHOT_URL})"
        print(f"openhire: auto-bootstrap failed ({_BOOTSTRAP_ERROR}). "
              "Run `ohp bootstrap` manually.", file=sys.stderr)
    finally:
        _INDEX_READY.set()


def _explain_bootstrap_failure(diagnosis: dict) -> dict:
    """An empty index that WE failed to fill says so, with the way out.

    diagnose_empty_search can only see that the index is empty; the download error lives
    on this thread. Without it the agent told the user "no HR roles in autonomous driving"
    when the truth was "GitHub is unreachable from here". The way out is spelled out because
    the agent is the one who has to relay it: a mirror the user trusts, or a direct crawl.
    """
    if diagnosis.get("index_empty") and _BOOTSTRAP_ERROR:
        diagnosis["bootstrap_error"] = _BOOTSTRAP_ERROR
        diagnosis["hint"] = (
            f"The index is empty because this server tried to download the public snapshot "
            f"and failed: {_BOOTSTRAP_ERROR}. This is a network problem, not a market answer — "
            "do not report it as 'no matches'. If GitHub is unreachable from this network "
            "(common in mainland China without a proxy), fetch the snapshot through a mirror "
            "the user trusts and point the server at it with OPENHIRE_SNAPSHOT_URL (a URL or "
            "a local file path), or run `ohp bootstrap --snapshot-url <url-or-path>`; or "
            "crawl the employers' own ATS directly with `ohp bootstrap --fresh` (20+ "
            "minutes, no GitHub needed). Restart the server afterwards. "
            "索引是空的，因为服务器自己下载公开快照失败了（GitHub 在本网络可能不通）。这是网络问题，"
            "不是「没有匹配的岗位」。可经你信任的镜像下载快照后 `ohp bootstrap --snapshot-url "
            "<地址或本地文件>`，或在 MCP 配置的 env 里设 OPENHIRE_SNAPSHOT_URL，或 "
            "`ohp bootstrap --fresh` 直接抓雇主 ATS。"
        )
    return diagnosis


def _start_bootstrap() -> None:
    """Kick off auto-bootstrap on a background thread if the index is empty.

    Startup must NOT block: `initialize` and `tools/list` need no data, and hosted
    marketplaces (ModelScope, Docker MCP Toolkit, Glama) time out a server that takes
    ~30 s to answer its first request. Tools that read data call `_await_index()`
    instead, so correctness is preserved without delaying discovery.

    Snapshot = public jobs/companies only, never user data (verified by
    install_snapshot). Skipped for Postgres and when OPENHIRE_NO_AUTO_BOOTSTRAP is set
    (tests/CI). All chatter goes to stderr — stdout belongs to the MCP protocol.
    """
    global _BOOTSTRAP_STARTED
    from sqlalchemy import func, select

    from . import config
    from .db.models import Company

    if _BOOTSTRAP_STARTED:
        return
    _BOOTSTRAP_STARTED = True
    if os.environ.get("OPENHIRE_NO_AUTO_BOOTSTRAP") or not config.DATABASE_URL.startswith("sqlite"):
        _INDEX_READY.set()
        return
    try:
        with session_scope() as s:
            n = s.execute(select(func.count()).select_from(Company)).scalar() or 0
    except Exception:
        n = 1  # can't tell: assume populated rather than clobber someone's index
    if n:
        _INDEX_READY.set()
        return

    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)  # no per-request INFO on stderr
    threading.Thread(target=_do_bootstrap, name="openhire-bootstrap", daemon=True).start()


def _await_index(timeout: float = 180.0) -> None:
    """Block until auto-bootstrap finishes.

    No-op unless `_start_bootstrap()` actually kicked one off — tools imported and called
    directly (tests, the CLI, an embedding host) must never wait on an event nobody will set.
    """
    if not _BOOTSTRAP_STARTED or _INDEX_READY.is_set():
        return
    _INDEX_READY.wait(timeout)


def serve(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the MCP server. transport: "stdio" (default) | "sse" | "streamable-http"."""
    init_db()
    _start_bootstrap()  # background: startup must stay instant for marketplace probes
    if transport != "stdio":
        mcp.settings.host = host
        mcp.settings.port = port
    mcp.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    serve()
