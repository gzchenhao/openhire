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
            "0. 我没说清是个人贡献者还是带团队、大概几年经验的，先问我一句，再把它作为 seniority 传给 search_jobs（ic 或 management；也可以用 intern、junior、senior、staff、lead、manager、director）。",
            "1. 用 search_jobs 搜：岗位名里的词放进 title，技能放进 skills，地点放进 location。结果为空就按 headline 告诉我是哪种「没有」，放宽一项再搜，并告诉我放宽了什么。",
            "2. 先给最相关的 5 条，每条六栏：岗位、公司与地点、薪资（没写就说雇主没写）、为什么匹配（matched_skills 加我说的条件）、投递前要确认什么（结果里的 check_before_apply）、投递链接；日期用结果里 dates_in_words 的原句。再问我要不要看更多。" + LENGTH_ZH,
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
        "0. If I have not said whether I want an individual-contributor or a management role, or how many years I have, "
        "ask me once, then pass it as seniority to search_jobs (ic or management; or intern, junior, senior, staff, lead, manager, director).",
        "1. Call search_jobs: words from the job title go in title, skills in skills, the place in location. "
        "If nothing comes back, tell me which kind of nothing it is (the headline), relax one filter, search again and tell me what you relaxed.",
        "2. Show the 5 most relevant first, six columns each: title, company and location, salary (say so when the employer states none), "
        "why it matches (matched_skills plus what I asked for), what to confirm before applying (check_before_apply), apply link; "
        "give the dates as the dates_in_words sentence. Then ask whether I want more. " + LENGTH_EN,
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
        "用 check_watches 查，先把结果里的 summary 原句告诉我；列出新岗（公司、岗位名、地点、发布日期、投递链接）和上次之后已经关闭的岗位；没有新岗就直说没有。is_first_pull 为真时，列出的是已有岗位的基线，不要说成新出现的。",
        "Call check_watches and start with its summary sentence; list the new postings (company, title, location, posting date, apply link) and the ones "
        "closed since the last check; if nothing is new, say so. When is_first_pull is true, the list is the baseline of postings already live: never present it as new.",
        "再用同一个指纹调 check_applications，告诉我投过的岗位里哪些已经下架、不用再等。 / Then call check_applications with the same fingerprint and tell me which postings I applied to have closed, so I can stop waiting.",
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


def before_apply(
    job: Annotated[str, Field(description="An OpenHire job id, or the employer and title as you saw them, e.g. unitree:123 or 宇树 运动控制工程师")],
    message: Annotated[str, Field(description="A recruiter message you were sent about it, pasted as is (optional; checked on your own machine only)")] = "",
) -> str:
    """Before you apply: is the posting still open, is the company real, and what to confirm. One pass, no verdict."""
    looks_like_id = len(job) < 80 and ":" in job and " " not in job
    if _zh(job, message):
        return "\n".join(filter(None, [
            f"我准备投这个岗位，投之前帮我查一遍：{job}",
            f"招聘方发给我的私信（传给 check_employer 的 message_text）：\n{message}" if message else "",
            "",
            "1. 岗位还在不在：" + ("用 search_jobs 找到这条（按公司和岗位名搜）" if not looks_like_id else f"用 search_jobs(company=…) 找到 job_id 为 {job} 的这条")
            + "，告诉我 dates_in_words 的原句、ghost_reason 和 check_before_apply 里的每一项；找不到就照结果的 headline 说清是哪种找不到，不要说成「已经招满」。",
            "2. 要求对不对得上：结果里的 requirements（最低学历、最少年限、是否校招或实习）原样告诉我；null 是启事没写，不是不要求。",
            "3. 公司真不真：用 check_employer 查" + (f"（job_id 传 {job}）" if looks_like_id else "（company 传公司名）")
            + "，每项原样报状态、来源、时间；outsourcing_words 有内容就提醒我，这可能是外包或派遣岗，劳动合同签在哪家要问清；pending_user 的项把官方网址给我，我自己去查。",
            "4. 投递链接：只认雇主自己的域名或招聘系统；结果里有 apply_channel_blocked 就别让我点。",
            "5. 最后用三行总结：还在不在、公司查到了什么、我投之前要问清的事。这是查证清单，不是判决，不要说「是骗子」或「很安全」。" + LENGTH_ZH,
            PRIVACY_ZH,
        ]))
    return "\n".join(filter(None, [
        f"I am about to apply for this posting; check it first: {job}",
        f"A recruiter message I was sent (pass it to check_employer as message_text):\n{message}" if message else "",
        "",
        "1. Is it still open: " + ("find it with search_jobs (by company and title)" if not looks_like_id else f"find job_id {job} with search_jobs(company=...)")
        + "; give me the dates_in_words sentence, ghost_reason and every check_before_apply item. If it cannot be found, say which "
        "kind of not found the headline gives; never call it filled.",
        "2. Do the requirements fit: quote its requirements (lowest degree, fewest years, campus or intern track); null means "
        "the posting does not say, not that nothing is required.",
        "3. Is the company real: call check_employer" + (f" (job_id {job})" if looks_like_id else " (company name)")
        + " and report every item with status, source and time; if outsourcing_words is not empty, tell me it may be an "
        "agency or outsourced role and that I should ask which company the contract is with; for pending_user items give me the official URL.",
        "4. Apply link: only the employer's own domain or ATS; if the result carries apply_channel_blocked, do not send me there.",
        "5. End with three lines: still open or not, what the company check found, what I should ask before applying. "
        "This is a checklist, not a verdict: never say it is a scam or that it is safe. " + LENGTH_EN,
        PRIVACY_EN,
    ]))


def shortlist(
    role: Annotated[str, Field(description="The job in your own words, e.g. 机器人算法 or robotics software engineer")],
    years: Annotated[str, Field(description="Years of experience, or 应届 / new grad (optional)")] = "",
    location: Annotated[str, Field(description="City or region (optional)")] = "",
) -> str:
    """Instead of sending 300 applications: drop the postings not worth sending to, and say why, before you apply."""
    if _zh(role, years, location):
        return "\n".join([
            "别让我海投。帮我把值得认真投的岗位挑出来，不值得投的剔掉并说明理由。",
            f"岗位：{role}；经验：{years or '没说，先问我一句'}；地点：{location or '不限'}",
            "",
            "1. 用 search_jobs 搜（岗位词放 title，地点放 location；应届就传 entry_level，否则按我的年限传 seniority），limit 100。",
            "2. 逐条剔掉这几类，每类数一下有多少条：requirements 里 min_years 超过我的年限的；requirements 里 min_degree 我够不上的（先问我学历）；check_before_apply 里提示在架超过 90 天的；雇主没标发布日期且索引首次看到已超过 90 天的。",
            "3. 剩下的按匹配度排，给我最多 10 条，每条一句话说为什么值得投，日期用 dates_in_words 的原句，附投递链接。",
            "4. 最后一段写「剔掉了多少条、各是什么原因」，让我知道省下了多少无效投递。",
            "5. 我投了哪几条，就用 check_applications 的 add_job_ids 记下来，以后我问「投的那些还在不在」就用它答。" + FINGERPRINT_ZH,
            LENGTH_ZH,
            PRIVACY_ZH,
        ])
    return "\n".join([
        "Do not let me mass-apply. Pick the postings worth a careful application, and drop the rest with the reason.",
        f"Role: {role}; experience: {years or 'not given, ask me once'}; location: {location or 'any'}",
        "",
        "1. Call search_jobs (role words in title, place in location; entry_level for a new grad, otherwise seniority from my years), limit 100.",
        "2. Drop, and count, each of: requirements.min_years above my years; requirements.min_degree I do not meet (ask my degree first); "
        "check_before_apply saying open over 90 days; no employer date and first seen by the index over 90 days ago.",
        "3. Rank what is left by fit and give me at most 10, one sentence each on why it is worth applying, dates as the dates_in_words sentence, apply link.",
        "4. End with how many you dropped and for which reasons, so I can see how many wasted applications this saved.",
        "5. When I say which ones I applied to, record them with check_applications add_job_ids, and use it later when I ask whether they are still open. " + FINGERPRINT_EN,
        LENGTH_EN,
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
            "1. 定方向：问我目标城市、岗位方向、个人贡献者还是带团队、年限、三到五个技能、不考虑的方向。",
            "2. 搜岗位：用 search_jobs 搜在架岗位（级别传 seniority），先给 5 条，每条带公司、地点、薪资、为什么匹配、投递前要确认什么（check_before_apply）、投递链接，日期用 dates_in_words 的原句；搜不到的公司用 list_portals 给我它们自己的招聘页。" + LENGTH_ZH,
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
        "1. Target: ask me for city, role, individual contributor or management, years, three to five skills, what to exclude.",
        "2. Search: search_jobs for live postings (level as seniority), 5 first, each with company, location, salary, why it matches, "
        "what to confirm before applying (check_before_apply) and the apply link, dates as the dates_in_words sentence; "
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
    ("before_apply", "投之前查一遍 · Check before you apply", before_apply),
    ("shortlist", "海投改精投 · Shortlist, don't mass-apply", shortlist),
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
