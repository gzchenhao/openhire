"""Built-in prompts: the questions a job seeker actually asks, packaged so a client can offer
them as one-click templates (Claude Desktop's "+" menu, a slash command in Claude Code or
VS Code). Howard asked on 2026-10-15 whether seekers have to know sentences such as
"add OKX's careers page to my index"; they do not: these templates carry the steps, the
server instructions tell the assistant to offer the next step itself, and the tool results
say what is possible next (read_board answers with add_to_my_index).

Each template renders in Chinese when any argument the user typed contains Chinese,
otherwise in English. Every one of them keeps the privacy rule in the text the assistant
reads: nothing about the user goes into a tool call.

Clients that only use tools (豆包, WorkBuddy, ChatGPT connectors) never see these; the
instructions and the tool results cover them.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field

_CJK = re.compile(r"[㐀-鿿豈-﫿]")

PRIVACY_ZH = "我的简历、名字、邮箱、电话一律不要传给任何工具；要和简历比对，就在你这边对照，不经过 OpenHire 的服务器。"
PRIVACY_EN = ("Never pass my résumé, name, email or phone to any tool; if you compare postings with my "
              "résumé, do it on your side, not through OpenHire's server.")
LENGTH_ZH = "在架时间长的岗位只说量到的事实（在架多少天、多久没更新），不要说它是假岗或僵尸岗。"
LENGTH_EN = ("For long-open postings say only what was measured (open N days, last touched M days ago); "
             "never call a posting fake or a ghost.")
FINGERPRINT_ZH = ("你生成一个 12 位以上的随机指纹（不含任何个人信息），把它原样告诉我、让我存好；"
                  "以后我说「看看我的雷达」，你就用这个指纹调 check_watches。")
FINGERPRINT_EN = ("Generate a random fingerprint of 12+ characters (nothing personal in it), show it to me "
                  "verbatim so I can keep it; when I later say \"check my radar\", call check_watches with it.")


def _zh(*values: str | None) -> bool:
    return any(v and _CJK.search(v) for v in values)


def job_radar(
    role: Annotated[str, Field(description="The job in your own words, e.g. 感知算法工程师 or robotics software engineer")],
    location: Annotated[str, Field(description="City or region, e.g. 上海, Hong Kong, remote (optional)")] = "",
    skills: Annotated[str, Field(description="Skills to match, comma separated, e.g. 点云, BEV, ROS (optional)")] = "",
) -> str:
    """Find matching postings now, then keep a standing radar on them."""
    if _zh(role, location, skills):
        return "\n".join([
            "帮我用 OpenHire 找工作。",
            f"岗位：{role}",
            f"地点：{location or '不限'}",
            f"技能：{skills or '不限'}",
            "",
            "1. 用 search_jobs 搜：岗位名里的词放进 title，技能放进 skills，地点放进 location。结果为空就放宽一项再搜，并告诉我放宽了什么。",
            "2. 列出最相关的 10 条：公司、岗位名、地点、原始发布日期、在架天数、投递链接。" + LENGTH_ZH,
            "3. 问我要不要建一个雷达。要的话用 watch_intent 登记同样的条件。" + FINGERPRINT_ZH,
            "4. 我想要的公司不在结果里，就问我它的招聘页网址，用 read_board 读，读得了再问我要不要用 add_employer 加进我这台电脑上的索引。",
            PRIVACY_ZH,
        ])
    return "\n".join([
        "Help me find a job with OpenHire.",
        f"Role: {role}",
        f"Location: {location or 'any'}",
        f"Skills: {skills or 'any'}",
        "",
        "1. Call search_jobs: words from the job title go in title, skills in skills, the place in location. "
        "If nothing comes back, relax one filter, search again and tell me what you relaxed.",
        "2. List the 10 most relevant: company, title, location, original posting date, days open, apply link. " + LENGTH_EN,
        "3. Ask whether I want a standing radar. If yes, register the same filters with watch_intent. " + FINGERPRINT_EN,
        "4. If an employer I care about is missing, ask me for its careers page, read it with read_board, and if "
        "it reads, offer add_employer to put it in the index on my machine.",
        PRIVACY_EN,
    ])


def track_employer(
    employer: Annotated[str, Field(description="The employer's name or its careers page URL, e.g. 智元机器人 or https://jobs.lever.co/okx")],
) -> str:
    """Everything one employer is hiring for, and a watch on it, wherever its board lives."""
    if _zh(employer):
        return "\n".join([
            f"帮我盯住这家公司的招聘：{employer}",
            "",
            "1. 先用 search_jobs(company=…) 查它在 OpenHire 索引里的在招岗位，有就列出来：岗位名、地点、发布日期、在架天数、投递链接。",
            "2. 索引里没有的话：",
            "   - 结果里带了「已知未收录」说明和招聘页链接（比如岗位在飞书或 BOSS 直聘上的公司），把链接和原因告诉我；你有浏览器工具就问我要不要你打开看。",
            "   - 否则用它的招聘页网址（我给了就用我给的，没给就在它官网上找，找不到再问我）调 read_board 读给我看。",
            "   - 读得了就问我要不要用 add_employer 把它加进我这台电脑上的索引：加了以后每周自动刷新，搜索和盯岗都算它。",
            "3. 问我要不要盯它的新岗。要的话用 watch_intent 登记 {\"company\": \"…\"}（没加进索引就用 {\"board_url\": \"…\"}）。" + FINGERPRINT_ZH,
            PRIVACY_ZH,
        ])
    return "\n".join([
        f"Keep track of this employer's hiring for me: {employer}",
        "",
        "1. Call search_jobs(company=...) for its live postings in the OpenHire index; list title, location, posting date, days open, apply link.",
        "2. If the index does not carry it:",
        "   - when the result carries a known-not-indexed note with a careers page link (an employer whose postings live on "
        "Feishu or BOSS直聘, for example), give me the link and the reason; if you have a browser tool, offer to open it.",
        "   - otherwise read its careers page with read_board (use the URL I gave; if none, look on its website, and ask me if you cannot find it).",
        "   - if the board reads, offer add_employer to put it in the index on my machine: it then refreshes weekly and counts in search and watches.",
        "3. Ask whether I want a watch on it. If yes, register {\"company\": \"...\"} with watch_intent "
        "({\"board_url\": \"...\"} if it was not added). " + FINGERPRINT_EN,
        PRIVACY_EN,
    ])


def vet_employer(
    employer: Annotated[str, Field(description="The employer's name, as on the posting")],
    posting: Annotated[str, Field(description="An OpenHire job id, or the posting text you were sent (optional)")] = "",
) -> str:
    """A checklist of what can be verified about an employer, never a verdict."""
    looks_like_id = bool(posting) and len(posting) < 80 and ":" in posting and " " not in posting
    if _zh(employer, posting):
        source = (f"岗位 id：{posting}（传给 job_id）" if looks_like_id
                  else (f"招聘启事原文（传给 posting_text）：\n{posting}" if posting else ""))
        return "\n".join(filter(None, [
            f"帮我查一下这家公司靠不靠谱：{employer}",
            source,
            "",
            "用 check_employer 查。",
            "- 清单上每一项都原样告诉我：状态、来源、时间。reason 是 network 的项，说明的是这次没连上来源，不是这家公司的问题。",
            "- 标 pending_user 的项，把它给的免费核验路径告诉我；你已经有天眼查之类的工具，就直接用它把工商登记补上。",
            "- 这是查证清单，不是判决：不要替我下「是骗子」或「很安全」的结论。",
            PRIVACY_ZH,
        ]))
    source = (f"OpenHire job id: {posting} (pass it as job_id)" if looks_like_id
              else (f"Posting text (pass it as posting_text):\n{posting}" if posting else ""))
    return "\n".join(filter(None, [
        f"Check this employer for me: {employer}",
        source,
        "",
        "Call check_employer.",
        "- Report every item as it comes back: status, source, time. An item whose reason is network means the source "
        "could not be reached this time; it says nothing about the employer.",
        "- For items marked pending_user, tell me the free verification paths it gives; if you already have a company-registry tool, use it.",
        "- This is a checklist, not a verdict: do not tell me the employer is a scam or that it is safe.",
        PRIVACY_EN,
    ]))


def radar_check(
    fingerprint: Annotated[str, Field(description="The fingerprint you saved when the radar was set up (optional if this conversation already has it)")] = "",
) -> str:
    """What is new on my radar since I last looked, and what has closed."""
    fp = fingerprint or "用这次对话里登记过的那个；没有就问我 / the one registered earlier in this conversation; if none, ask me"
    return "\n".join([
        "看看我的 OpenHire 雷达有没有新岗。 / Check my OpenHire radar for new postings.",
        f"指纹 / Fingerprint: {fp}",
        "",
        "用 check_watches 查，列出新岗（公司、岗位名、地点、发布日期、投递链接）和上次之后已经关闭的岗位；没有新岗就直说没有。",
        "Call check_watches; list the new postings (company, title, location, posting date, apply link) and the ones "
        "closed since the last check; if nothing is new, say so.",
        "用我写字的语言回答。 / Answer in the language I write in.",
    ])


def new_this_week(
    role: Annotated[str, Field(description="Job words to filter on, e.g. 规控 or perception (optional)")] = "",
    location: Annotated[str, Field(description="City or region (optional)")] = "",
    company: Annotated[str, Field(description="One employer (optional)")] = "",
) -> str:
    """Postings first published in the last 7 days, grouped by employer."""
    if _zh(role, location, company):
        return "\n".join([
            "OpenHire 索引里最近 7 天新发的岗位。",
            f"岗位：{role or '不限'}；地点：{location or '不限'}；公司：{company or '不限'}",
            "",
            "用 search_jobs 按这些条件搜（limit 100，不够就用 offset 翻页），只留 datePosted 在最近 7 天内的，按公司分组列出：岗位名、地点、发布日期、投递链接。",
            "date_signal 是 not_reported_by_ats 的行，日期是索引第一次看到它的日子，不是雇主自己的发布日，单独列出并说明。",
            PRIVACY_ZH,
        ])
    return "\n".join([
        "Postings first published in the last 7 days in the OpenHire index.",
        f"Role: {role or 'any'}; location: {location or 'any'}; company: {company or 'any'}",
        "",
        "Call search_jobs with these filters (limit 100, page with offset if needed), keep only rows whose datePosted "
        "is within the last 7 days, and group them by employer: title, location, posting date, apply link.",
        "Rows whose date_signal is not_reported_by_ats carry the day this index first saw them, not the employer's own "
        "posting date: list them separately and say so.",
        PRIVACY_EN,
    ])


CHECKLIST_URL = "https://gzchenhao.github.io/openhire/checklist.html"
CHECKLIST_URL_CN = "https://openhire-vlny.onrender.com/checklist"


def job_checklist(
    stage: Annotated[str, Field(description="Where you are: 刚开始 / 在投 / 收到 offer, or starting / applying / got an offer (optional)")] = "",
) -> str:
    """The free job-search checklist: each step, what OpenHire does for you, where to do the rest, and the anti-scam steps."""
    if _zh(stage) or not stage:
        return "\n".join([
            f"我在找工作，阶段：{stage or '刚开始'}。请按 OpenHire 的求职清单带我走（完整版 {CHECKLIST_URL} ，国内打不开就用 {CHECKLIST_URL_CN} ；每条都说清是你替我做，还是我去哪里做）：",
            "",
            "1. 定方向：问我目标城市、岗位方向、年限、三到五个技能、不考虑的方向。",
            "2. 搜岗位：用 search_jobs 搜在架岗位，每条带公司、地点、原始发布日期、在架天数、投递链接；搜不到的公司用 list_portals 给我它们自己的招聘页。" + LENGTH_ZH,
            "3. 查公司：我挑中哪家，用 check_employer 查一遍；结果里 pending_user 的项，把官方网址原样给我，我自己去查（工商登记：国家企业信用信息公示系统、爱企查、天眼查自己的免费服务；香港公司：公司註冊處）。",
            "4. 反诈骗三步：① 要我先交钱、先出境面试、先交护照、包机票高薪的，先停下来查；② 投递链接必须在雇主自己的域名或招聘系统上，别的一律不点；③ 拿不准的电话、网址、收款账户，大陆用国家反诈中心 App 或 12321 举报平台，香港用防騙視伏器。",
            "5. 投递：我自己点投递链接去投，你不替我投，也不碰我的简历。要记录就用 authorize_application 记一条授权。",
            "6. 盯岗：用 watch_intent 把这个意向设成雷达。" + FINGERPRINT_ZH,
            "7. 面试与 offer：合同、社保、试用期按人社部 12333 热线的口径核对；公司有法院记录可在中国裁判文书网查。",
            PRIVACY_ZH,
        ])
    return "\n".join([
        f"I am looking for a job, stage: {stage or 'starting'}. Walk me through OpenHire's job-search checklist (full page {CHECKLIST_URL}); for every step say whether you do it for me or where I do it myself:",
        "",
        "1. Target: ask me for city, role, years, three to five skills, what to exclude.",
        "2. Search: search_jobs for live postings with company, location, original posting date, days open and apply link; "
        "for employers it cannot read, list_portals gives me their own careers pages. " + LENGTH_EN,
        "3. Check the employer: check_employer on the one I pick; for every pending_user item give me the official URL "
        "verbatim and I look it up myself (company registers, Hong Kong Companies Registry, OpenCorporates).",
        "4. Anti-scam, three steps: stop and check if I am asked to pay first, travel abroad for an interview or hand over "
        "a passport; apply only through the employer's own domain or ATS; report doubtful phone numbers, sites or "
        "accounts to the local anti-fraud service (Hong Kong: Scameter).",
        "5. Apply: I click the apply link myself; you never submit for me and never touch my résumé. "
        "authorize_application only records my authorization.",
        "6. Radar: watch_intent on the same filters. " + FINGERPRINT_EN,
        "7. Offer: check the contract, social insurance and probation terms against the local labour authority's guidance.",
        PRIVACY_EN,
    ])


PROMPTS = (
    ("job_checklist", "求职清单 · Job-search checklist", job_checklist),
    ("job_radar", "找工作雷达 · Job radar", job_radar),
    ("track_employer", "盯一家公司 · Track one employer", track_employer),
    ("vet_employer", "查这家公司靠不靠谱 · Check an employer", vet_employer),
    ("radar_check", "看看我的雷达 · What's new on my radar", radar_check),
    ("new_this_week", "本周新岗 · New this week", new_this_week),
)


def register(mcp) -> None:
    for name, title, fn in PROMPTS:
        try:
            decorate = mcp.prompt(name=name, title=title, description=fn.__doc__)
        except TypeError:
            # An mcp SDK older than prompt titles (the 2025-06 spec) is still >= our floor
            # of 1.2: the prompt is listed under its name instead of failing the server.
            decorate = mcp.prompt(name=name, description=fn.__doc__)
        decorate(fn)
