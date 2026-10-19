"""Known-but-not-indexed employers: "not in the index, and here is why".

The index covers employers whose public ATS answers a plain GET or POST with the postings
in the clear (Greenhouse, Lever, Ashby, Beisen, Moka). A group of the hottest Chinese
employers in our target industry run their careers sites on Feishu Recruitment (飞书招聘),
whose job-list API requires a client-computed request signature (`_signature`) and loads a
captcha SDK. reports/014 and reports/020 settled the rule: a request signature is access
control, not a transport encoding, and we do not work around it. So those employers are
absent from the index on purpose, and this file says so.

Without this registry a job seeker asking for Momenta got the same generic "not indexed"
hint as a typo, and get_company_info returned ERR_COMPANY_NOT_FOUND, so they could not
tell "not in this index yet" from "we know exactly why". This is that answer, made
first-class: the careers portal to go to directly, the honest reason, and the one path
that would change it (the employer authorising read-only access).

This file is DECLARATIVE. Nothing here is crawled, fetched or inferred at runtime. Each
`careers_url` was confirmed by ONE plain GET of the portal root, and `confirmed_by` says
what that GET actually showed: for nine entries the `<title>` names the employer; for
SenseTime the title was not retrieved and the evidence is the feishucdn asset fingerprint
on the employer's own host (reports/014 showed that a 200 alone is not enough:
`horizon.jobs.feishu.cn` is a different company). Where we could not confirm a host, the
URL stays None rather than a guess.

Entries are removed the day an employer becomes indexable (they authorise the scopes, or
move to an ATS that is publicly readable), because `service` consults the live index first
and only falls back to this list.

One entry is not Feishu: NIO 蔚来. Its own careers page publishes the roster in the clear,
and its edge security policy blocks this crawler (HTTP 567). Same rule, different door:
a bot-management policy the site owner configured is access control too (reports/020),
so the adapter is built and parked and the entry says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FEISHU_ATS = "feishu"

# One honest sentence, reused verbatim on every Feishu entry so the wording cannot drift.
FEISHU_REASON = (
    "This employer's careers site runs on Feishu Recruitment (飞书招聘), whose job-list API "
    "requires a client-computed request signature; we treat that as access control and do "
    "not work around it, so none of its postings are in this index."
)
# The same sentence for a person at the CLI, who gets the portal and nothing else.
FEISHU_REASON_ZH = "招聘站要求请求签名，我们视为访问控制、不绕过"

# The Feishu open-platform scopes that would let an employer grant read-only access to
# their public job posts without exposing anything else on their tenant. This is the
# employer's decision to make, and it is the only route that changes the answer above.
FEISHU_OPT_IN_SCOPES = ("hire:site:readonly", "hire:site_job_post:readonly")

FEISHU_OPT_IN = {
    "who": "the employer",
    "what": (
        "Authorise the read-only Feishu open-platform scopes for their recruitment site "
        "and job posts. Both are read-only: they expose the public careers site and its "
        "published postings, nothing about candidates, and they cannot buy rank or a "
        "lower ghost_score (both are locked pure functions)."
    ),
    "scopes": list(FEISHU_OPT_IN_SCOPES),
    "how": (
        "Open an employer-claim issue at https://github.com/gzchenhao/openhire/issues "
        "(template: Employer claim) or email gdchenhao@qq.com from a corporate address "
        "with the subject 'Employer claim'. Identity is verified by corporate domain, "
        "never by payment."
    ),
    # One clause for the hint sentence: "The employer can change this by <summary>."
    "summary": (
        "authorising the read-only Feishu open-platform scopes "
        + ", ".join(FEISHU_OPT_IN_SCOPES)
    ),
}

NIO_ATS = "first-party site (blocked by the site's security policy, HTTP 567)"
NIO_REASON = (
    "the employer's own careers page publishes the postings, but its edge security policy "
    "blocks this crawler; we do not work around security controls; the adapter is built "
    "and parked until NIO allowlists or authorizes us"
)
NIO_REASON_ZH = "雇主自己的招聘页公开了岗位，但站点的安全策略拦截了我们的抓取器（HTTP 567），我们不绕过安全控制"
NIO_OPT_IN = {
    "who": "the employer",
    "what": (
        "Allowlist this crawler on the careers site's edge security policy (the block "
        "page carries a request ID to quote to the site owner), or authorise the read-only "
        "Feishu open-platform scopes for the recruitment site and job posts. Either is "
        "read-only: it exposes the public roster, nothing about candidates, and it cannot "
        "buy rank or a lower ghost_score (both are locked pure functions)."
    ),
    "scopes": list(FEISHU_OPT_IN_SCOPES),
    "how": FEISHU_OPT_IN["how"],
    "summary": (
        "allowlisting this crawler on its careers site, or authorising the read-only "
        "Feishu open-platform scopes " + ", ".join(FEISHU_OPT_IN_SCOPES)
    ),
}


# --- Employers whose own site offers no readable job list (2026-10-08 survey, reports/060) ---
# A one-GET survey of 28 small employers in our target industry found no schema.org JobPosting
# markup anywhere; the Chinese ones either run Feishu Recruitment, publish only on the
# BOSS直聘 platform, or keep a careers page with no job list. The registry says which.
OWN_PAGE_ATS = "first-party page without a readable job list"
OWN_PAGE_OPT_IN = {
    "who": "the employer",
    "what": (
        "Publish the postings on the employer's own site in a machine-readable form "
        "(schema.org JobPosting JSON-LD, or a JSON feed) and tell us the URL; or move them to "
        "an ATS whose public board API we already read (Greenhouse, Lever, Ashby, Beisen, "
        "Moka); or authorise the read-only Feishu open-platform scopes for a recruitment "
        "site. All three are read-only: they expose the public postings, nothing about "
        "candidates, and they cannot buy rank or a lower ghost_score (both are locked pure "
        "functions)."
    ),
    "scopes": list(FEISHU_OPT_IN_SCOPES),
    "how": FEISHU_OPT_IN["how"],
    "summary": (
        "publishing a machine-readable careers page, moving to a publicly readable ATS, "
        "or authorising the read-only Feishu open-platform scopes "
        + ", ".join(FEISHU_OPT_IN_SCOPES)
    ),
}
PLATFORM_ONLY_ATS = "BOSS直聘 only (a platform, not the employer's own system)"
PLATFORM_ONLY_REASON = (
    "this employer publishes its postings only on the BOSS直聘 platform and its own site has "
    "no careers page; this index reads employers' own systems and never platforms, so none "
    "of its postings are here"
)
PLATFORM_ONLY_REASON_ZH = "雇主只在 BOSS 直聘上发布岗位，官网没有招聘页；我们只读雇主自己的系统，不读平台"

# A company that no longer exists is still something a seeker types. The entry keeps the
# dated facts and offers no opt-in, because there is nobody left to opt in.
CEASED_ATS = "none (the company has ceased operations)"

# What a person sees on the portal in a browser without logging in. Only what was seen:
# the Feishu line rests on one portal opened in a browser on 2026-10-15 (星动纪元, by the
# maintainer's local session, no login, no API call); an entry can override it.
PORTAL_VIEW = {
    FEISHU_ATS: (
        "In a browser, without logging in: the job list and each posting's full description. "
        "The pages show no posting date. (Checked on one Feishu portal on 2026-10-15.)"
    ),
}
PORTAL_VIEW_ZH = {
    FEISHU_ATS: "浏览器打开、不登录：能看岗位列表和每条的完整职位描述；页面上没有发布日期（2026-10-15 在一家飞书门户上核过）",
}

# The three sectors this index covers, and what a seeker types for each.
SECTORS = ("autonomous_driving", "embodied_ai", "ai_infra")
SECTOR_ALIASES = {
    "autonomous_driving": ("autonomous driving", "autonomous_driving", "av", "self-driving", "adas",
                           "自动驾驶", "智驾", "智能驾驶"),
    "embodied_ai": ("embodied ai", "embodied_ai", "embodied", "robotics", "robot", "humanoid",
                    "具身", "具身智能", "机器人", "人形机器人"),
    "ai_infra": ("ai infra", "ai_infra", "ai", "llm", "foundation models", "大模型", "人工智能"),
}
SECTOR_NAMES_ZH = {"autonomous_driving": "自动驾驶", "embodied_ai": "具身智能", "ai_infra": "AI 基础设施与大模型"}


@dataclass(frozen=True)
class NotIndexedEmployer:
    id: str                       # our stable slug, same convention as companies.id
    name: str                     # bilingual display name, as the index would show it
    aliases: tuple[str, ...]      # what a seeker actually types, in either language
    careers_url: str | None       # the employer's own portal; None when unconfirmed
    # What the one confirming GET showed. "title" means the page <title> named the
    # employer; anything else names the weaker evidence so nobody claims a title for it.
    confirmed_by: str = "title"
    ats: str = FEISHU_ATS
    reason: str = FEISHU_REASON
    reason_zh: str = FEISHU_REASON_ZH
    employer_opt_in: dict = field(default_factory=lambda: dict(FEISHU_OPT_IN))
    sector: str = ""              # one of SECTORS
    last_checked: str = "2026-09-23"   # the day careers_url was last confirmed
    portal_view: str | None = None     # overrides PORTAL_VIEW[ats]
    portal_view_zh: str | None = None

    @property
    def visible_without_login(self) -> str | None:
        return self.portal_view or PORTAL_VIEW.get(self.ats)

    @property
    def visible_without_login_zh(self) -> str | None:
        return self.portal_view_zh or PORTAL_VIEW_ZH.get(self.ats)

    @property
    def ceased(self) -> bool:
        return self.ats == CEASED_ATS

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "aliases": list(self.aliases),
            "careers_url": self.careers_url,
            "ats": self.ats,
            "indexed": False,
            "reason": self.reason,
            "reason_zh": self.reason_zh,
            "employer_opt_in": dict(self.employer_opt_in),
            "sector": self.sector,
            "visible_without_login": self.visible_without_login,
            "visible_without_login_zh": self.visible_without_login_zh,
            "last_checked": self.last_checked,
        }


# Portal roots. Confirmed by <title> on 2026-09-23 unless the entry's confirmed_by says
# otherwise.
NOT_INDEXED: tuple[NotIndexedEmployer, ...] = (
    NotIndexedEmployer(
        id="momenta", name="Momenta 魔门塔",
        aliases=("momenta", "魔门塔", "初速度"),
        careers_url="https://momenta.jobs.feishu.cn/",          # reports/014: "Momenta Talent"
        sector="autonomous_driving",
    ),
    NotIndexedEmployer(
        id="ponyai", name="小马智行 Pony.ai",
        aliases=("pony.ai", "pony ai", "ponyai", "pony", "小马智行", "小马"),
        careers_url="https://ponyai.jobs.feishu.cn/ponyai/",    # reports/014
        sector="autonomous_driving",
    ),
    NotIndexedEmployer(
        id="agibot", name="智元机器人 AgiBot",
        aliases=("agibot", "agirobot", "智元机器人", "智元"),
        careers_url="https://agirobot.jobs.feishu.cn/",
        sector="embodied_ai",
    ),
    NotIndexedEmployer(
        id="minimax", name="MiniMax 稀宇科技",
        aliases=("minimax", "稀宇科技", "稀宇"),
        careers_url="https://vrfi1sk8a0.jobs.feishu.cn/",       # <title>加入MiniMax</title>
        sector="ai_infra",
    ),
    NotIndexedEmployer(
        id="zhipu", name="智谱 Zhipu AI",
        aliases=("zhipu", "zhipu ai", "zhipuai", "智谱", "智谱华章", "智谱ai"),
        careers_url="https://zhipu-ai.jobs.feishu.cn/",         # <title>加入北京智谱华章科技有限公司</title>
        sector="ai_infra",
    ),
    NotIndexedEmployer(
        id="sensetime", name="商汤科技 SenseTime",
        aliases=("sensetime", "商汤科技", "商汤"),
        # Custom domain. The page <title> was NOT retrieved; what the GET showed is the
        # Feishu Recruitment white label's feishucdn asset fingerprint served from the
        # employer's own host, which is what puts it on this list.
        careers_url="https://hr-jobs.sensetime.com/",
        confirmed_by="feishucdn asset fingerprint on hr-jobs.sensetime.com; title not retrieved",
        sector="ai_infra",
    ),
    NotIndexedEmployer(
        id="limx", name="逐际动力 LimX Dynamics",
        aliases=("limx", "limx dynamics", "limxdynamics", "逐际动力", "逐际"),
        careers_url="https://career.limxdynamics.com/",         # reports/014: Feishu white label
        sector="embodied_ai",
    ),
    NotIndexedEmployer(
        id="xsquare", name="自变量机器人 X Square Robot",
        aliases=("x square", "xsquare", "x square robot", "x2 robot", "x2-robot",
                 "自变量机器人", "自变量"),
        careers_url="https://x2-robot.jobs.feishu.cn/",         # <title>加入自变量机器人 | 社会招聘</title>
        sector="embodied_ai",
    ),
    NotIndexedEmployer(
        id="spiritai", name="千寻智能 Spirit AI",
        aliases=("spirit ai", "spiritai", "spirit-ai", "千寻智能", "千寻"),
        careers_url="https://nwd4iy9rd2s.jobs.feishu.cn/",      # <title>加入千寻智能（杭州）科技有限公司</title>
        sector="embodied_ai",
    ),
    NotIndexedEmployer(
        id="booster", name="加速进化 Booster Robotics",
        aliases=("booster", "booster robotics", "加速进化"),
        careers_url="https://booster.jobs.feishu.cn/",          # <title>Join Booster Robotics</title>
        sector="embodied_ai",
    ),
    # 2026-10-08 survey (reports/060). Confirmed by <title> on that day.
    NotIndexedEmployer(
        id="noematrix", name="穹彻智能 Noematrix",
        aliases=("noematrix", "穹彻智能", "穹彻"),
        # Its own page (www.noematrix.ai/join-us, <title>加入我们 | 穹彻智能</title>) links to
        # this Feishu tenant, which belongs to 非夕 Flexiv: <title>加入穹彻智能</title>.
        careers_url="https://flexivrobotics.jobs.feishu.cn/971932",
        sector="embodied_ai", last_checked="2026-10-08",
    ),
    NotIndexedEmployer(
        id="engineai", name="众擎机器人 EngineAI",
        aliases=("engineai", "engine ai", "众擎机器人", "众擎"),
        careers_url="https://dx3a2bminsq.jobs.feishu.cn/",      # <title>加入深圳市众擎机器人科技有限公司</title>
        sector="embodied_ai", last_checked="2026-10-08",
    ),
    # Not Feishu. The page itself is public (a plain curl GET on 2026-09-23 returned the
    # 1,784-row roster inside __NEXT_DATA__, see ats/nio.py), and the same GET from this
    # crawler's HTTP client answers 567 with a Tencent Cloud EdgeOne security-policy page.
    # The adapter and its tests exist; seed/candidates.py keeps the row parked.
    NotIndexedEmployer(
        id="nio", name="蔚来 NIO",
        aliases=("蔚来", "nio", "蔚来汽车", "nio inc"),
        careers_url="https://www.nio.cn/careers/jobs",
        confirmed_by=(
            "plain GET on 2026-09-23 returned the roster to curl and HTTP 567 (EdgeOne "
            "security policy page) to this crawler's client; see ats/nio.py"
        ),
        ats=NIO_ATS,
        reason=NIO_REASON,
        reason_zh=NIO_REASON_ZH,
        employer_opt_in=dict(NIO_OPT_IN),
        sector="autonomous_driving",
        portal_view="The careers page lists every posting publicly; a browser shows it (a plain request on 2026-09-23 returned the full roster).",
        portal_view_zh="招聘页公开列出全部岗位，浏览器就能看（2026-09-23 一次普通请求拿到了完整名单）",
    ),
    # --- 2026-10-08 survey (reports/060): no readable job list on the employer's own site ---
    NotIndexedEmployer(
        id="deeprobotics", name="云深处科技 DeepRobotics",
        aliases=("deeprobotics", "deep robotics", "云深处科技", "云深处"),
        careers_url="https://www.deeprobotics.cn/",
        confirmed_by=(
            "homepage <title> names the employer; its 加入我们 link goes to zhipin.com "
            "(BOSS直聘) and the in-page jobs anchor is commented out; there is no careers page"
        ),
        ats=PLATFORM_ONLY_ATS,
        reason=PLATFORM_ONLY_REASON,
        reason_zh=PLATFORM_ONLY_REASON_ZH,
        employer_opt_in=dict(OWN_PAGE_OPT_IN),
        sector="embodied_ai", last_checked="2026-10-08",
        portal_view="The link is the employer's homepage; its 加入我们 link leads to BOSS直聘, a platform that decides what it shows without a login.",
        portal_view_zh="链接是公司官网；官网的「加入我们」指向 BOSS 直聘（平台，不登录能看到多少由 BOSS 直聘决定）",
    ),
    NotIndexedEmployer(
        id="ai2robotics", name="智平方 AI2 Robotics",
        aliases=("ai2robotics", "ai2 robotics", "ai² robotics", "智平方科技", "智平方"),
        careers_url="https://ai2robotics.com/joinus/",           # <title>加入我们 - 智平方科技</title>
        ats=OWN_PAGE_ATS,
        reason=(
            "the employer's own careers page lists no postings and takes applications by "
            "email, so there is nothing machine-readable for this index to read"
        ),
        reason_zh="雇主官网的招聘页没有岗位列表，只给了投递邮箱，没有可读的岗位数据",
        employer_opt_in=dict(OWN_PAGE_OPT_IN),
        sector="embodied_ai", last_checked="2026-10-08",
        portal_view="The page lists no postings; it gives an email address for applications.",
        portal_view_zh="页面没有岗位列表，只给了投递邮箱",
    ),
    NotIndexedEmployer(
        id="qcraft", name="轻舟智航 QCraft",
        aliases=("qcraft", "轻舟智航", "轻舟"),
        careers_url="https://www.qcraft.ai/cn/careers",          # <title>轻舟智航-成为全球领先的通用物理AI公司</title>
        ats=OWN_PAGE_ATS,
        reason=(
            "the employer's own careers page collects résumés through a Feishu form and lists "
            "no postings, so there is nothing machine-readable for this index to read"
        ),
        reason_zh="雇主官网的招聘页只放了一个飞书收简历表单，没有岗位列表",
        employer_opt_in=dict(OWN_PAGE_OPT_IN),
        sector="autonomous_driving", last_checked="2026-10-08",
        portal_view="The page lists no postings; it collects résumés through a Feishu form.",
        portal_view_zh="页面没有岗位列表，只有一个飞书收简历表单",
    ),
    NotIndexedEmployer(
        id="phigent", name="鉴智机器人 PhiGent Robotics",
        aliases=("phigent", "phigent robotics", "鉴智机器人", "鉴智"),
        careers_url="https://www.phigent.ai/",                   # <title>PhiGent</title>, a 439-byte JS shell
        ats=OWN_PAGE_ATS,
        reason=(
            "the employer's own site is a JavaScript application that exposes no job list to "
            "a plain GET; we do not execute a site's scripts, so there is nothing for this "
            "index to read"
        ),
        reason_zh="雇主官网是纯 JS 应用，普通请求拿不到岗位列表；我们不执行站点脚本",
        employer_opt_in=dict(OWN_PAGE_OPT_IN),
        sector="autonomous_driving", last_checked="2026-10-08",
        portal_view="A JavaScript site that a browser renders; whether it shows a job list has not been checked.",
        portal_view_zh="纯 JS 网站，浏览器能打开；里面有没有岗位列表还没核过",
    ),
    NotIndexedEmployer(
        id="noetix", name="松延动力 Noetix Robotics",
        aliases=("noetix", "noetix robotics", "松延动力", "松延"),
        careers_url="https://www.noetixrobotics.com/recruitment/jobs",  # <title>职位列表-北京松延动力科技集团股份有限公司官网</title>
        ats=OWN_PAGE_ATS,
        reason=(
            "the employer's own careers page loads its postings from the site's own API, "
            "which the site's robots.txt disallows; we honour robots.txt, so none of its "
            "postings are here"
        ),
        reason_zh="雇主官网的岗位列表来自它自己的接口，而站点 robots.txt 禁止抓取该接口；我们遵守 robots",
        employer_opt_in=dict(OWN_PAGE_OPT_IN),
        sector="embodied_ai", last_checked="2026-10-08",
        portal_view="A browser shows the job list; the page loads it from the site's own API, which robots.txt closes to crawlers.",
        portal_view_zh="浏览器打开能看到岗位列表；页面从站点自己的接口加载，robots.txt 不让爬虫读这个接口",
    ),
    # A former employer. Dated facts only; no opt-in because there is nobody to opt in.
    NotIndexedEmployer(
        id="haomo", name="毫末智行 HAOMO.AI",
        aliases=("haomo", "haomo.ai", "haomo ai", "毫末智行", "毫末"),
        careers_url=None,
        confirmed_by="not applicable: the company has ceased operations",
        ats=CEASED_ATS,
        reason=(
            "the company has ceased operations: a work-stoppage notice went out on 2025-11-29 "
            "(reported by 腾讯新闻 and 新浪科技), its Moka careers portal was retired by "
            "2026-09-02, and haomo.ai redirected to an unrelated site by 2026-10-08; there is "
            "nothing to index"
        ),
        reason_zh="公司已停止运营（2025-11-29 停工通知，媒体公开报道；Moka 招聘门户 2026-09-02 已关停，官网域名 2026-10 已易主）",
        employer_opt_in={},
        sector="autonomous_driving", last_checked="2026-10-08",
    ),
)

@dataclass(frozen=True)
class SecondPortal:
    """An employer this index DOES read, that also lists postings on a portal it cannot.
    Kept apart from NOT_INDEXED on purpose: calling it "not indexed" would be false, and
    its id would collide with the indexed company's. get_company_info and list_portals
    show the second portal next to what the index holds."""
    company_id: str               # the indexed company's id
    name: str
    careers_url: str
    confirmed_by: str
    last_checked: str
    sector: str
    note: str
    note_zh: str
    ats: str = FEISHU_ATS

    @property
    def visible_without_login(self) -> str | None:
        return PORTAL_VIEW.get(self.ats)

    @property
    def visible_without_login_zh(self) -> str | None:
        return PORTAL_VIEW_ZH.get(self.ats)

    def as_dict(self) -> dict:
        return {
            "company_id": self.company_id,
            "name": self.name,
            "careers_url": self.careers_url,
            "ats": self.ats,
            "sector": self.sector,
            "note": self.note,
            "note_zh": self.note_zh,
            "visible_without_login": self.visible_without_login,
            "visible_without_login_zh": self.visible_without_login_zh,
            "last_checked": self.last_checked,
        }


SECOND_PORTALS: tuple[SecondPortal, ...] = (
    # 2026-10-15, the maintainer's local session (reports/081): opened in a browser without
    # logging in, robots.txt absent, "开启新的工作（19）" with full descriptions, no dates.
    SecondPortal(
        company_id="robotera", name="星动纪元 Robot Era",
        careers_url="https://k0fqxcszc9.jobs.feishu.cn/index",
        confirmed_by="opened in a browser without logging in on 2026-10-15: 19 postings listed under the employer's name",
        last_checked="2026-10-15", sector="embodied_ai",
        note=("The index reads this employer's Moka board; it also lists postings on a Feishu "
              "portal this index cannot read (19 on 2026-10-15). Postings that are only there are "
              "not in search results."),
        note_zh="索引读的是它的 Moka 招聘页；它另有一个飞书招聘门户（2026-10-15 列着 19 条），我们读不了，只在那里的岗位搜不到",
    ),
)
_SECOND_BY_COMPANY: dict[str, list[SecondPortal]] = {}
for _p in SECOND_PORTALS:
    _SECOND_BY_COMPANY.setdefault(_p.company_id, []).append(_p)


def second_portals_for(company_id: str) -> list[SecondPortal]:
    return list(_SECOND_BY_COMPANY.get(company_id, ()))


def second_portals(sector: str | None = None) -> list[SecondPortal]:
    out = [p for p in SECOND_PORTALS if sector is None or p.sector == sector]
    return sorted(out, key=lambda p: (SECTORS.index(p.sector) if p.sector in SECTORS else 99, p.name.casefold()))


_BY_ID = {e.id: e for e in NOT_INDEXED}


def _fold(s: str) -> str:
    return " ".join((s or "").casefold().split())


def lookup(query: str) -> list[NotIndexedEmployer]:
    """Resolve what a caller typed against the registry, the way resolve_company does.

    Exact hits on id / name / alias win outright. Otherwise a caseless substring of the
    query inside a name or alias, or of an alias inside the query ("Momenta 招聘"), so a
    seeker who types either half of a bilingual name still lands. Single characters are
    never matched: "a" is not a company. The alias-inside-query direction needs an alias
    of at least three characters: the two-character short forms ("小马", "千寻") still
    hit exactly, but "千寻位置" and "小马拉车" are other companies, not questions about
    these ones. A Latin alias inside the query must also sit on word boundaries: "nio"
    is inside "senior" and "union", and neither is a question about NIO.
    """
    q = _fold(query)
    if len(q) < 2:
        return []
    exact = [
        e for e in NOT_INDEXED
        if q == e.id or q == _fold(e.name) or any(q == _fold(a) for a in e.aliases)
    ]
    if exact:
        return exact
    out: list[NotIndexedEmployer] = []
    for e in NOT_INDEXED:
        names = [e.id, _fold(e.name), *(_fold(a) for a in e.aliases)]
        if any(q in n for n in names) or any(len(n) >= 3 and _inside(n, q) for n in names):
            out.append(e)
    return out


def _inside(alias: str, query: str) -> bool:
    """`alias` occurs in `query`; on word boundaries when the alias is Latin text."""
    if alias.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", query) is not None
    return alias in query


def by_id(employer_id: str) -> NotIndexedEmployer | None:
    return _BY_ID.get((employer_id or "").strip().casefold())


def parse_sector(text: str | None) -> str | None:
    """What a seeker typed ("具身", "AV", "embodied_ai") to one of SECTORS; None for no filter.
    Raises ValueError for words that name no sector this index covers."""
    if text is None or not str(text).strip():
        return None
    t = _fold(str(text))
    for sector, aliases in SECTOR_ALIASES.items():
        if t == sector or t in (_fold(a) for a in aliases):
            return sector
    raise ValueError(text)


def portals(sector: str | None = None) -> list[NotIndexedEmployer]:
    """The link directory: employers in our sectors whose postings this index cannot read,
    each with its own careers portal. A company that has ceased operations is left out (its
    entry stays for lookups, so a seeker who names it still hears what happened), and so is
    any entry without a confirmed URL. Sorted by sector, then name."""
    out = [e for e in NOT_INDEXED if e.careers_url and not e.ceased and (sector is None or e.sector == sector)]
    return sorted(out, key=lambda e: (SECTORS.index(e.sector) if e.sector in SECTORS else 99, e.name.casefold()))
