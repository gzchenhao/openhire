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
        }


# Portal roots. Confirmed by <title> on 2026-09-23 unless the entry's confirmed_by says
# otherwise.
NOT_INDEXED: tuple[NotIndexedEmployer, ...] = (
    NotIndexedEmployer(
        id="momenta", name="Momenta 魔门塔",
        aliases=("momenta", "魔门塔", "初速度"),
        careers_url="https://momenta.jobs.feishu.cn/",          # reports/014: "Momenta Talent"
    ),
    NotIndexedEmployer(
        id="ponyai", name="小马智行 Pony.ai",
        aliases=("pony.ai", "pony ai", "ponyai", "pony", "小马智行", "小马"),
        careers_url="https://ponyai.jobs.feishu.cn/ponyai/",    # reports/014
    ),
    NotIndexedEmployer(
        id="agibot", name="智元机器人 AgiBot",
        aliases=("agibot", "agirobot", "智元机器人", "智元"),
        careers_url="https://agirobot.jobs.feishu.cn/",
    ),
    NotIndexedEmployer(
        id="minimax", name="MiniMax 稀宇科技",
        aliases=("minimax", "稀宇科技", "稀宇"),
        careers_url="https://vrfi1sk8a0.jobs.feishu.cn/",       # <title>加入MiniMax</title>
    ),
    NotIndexedEmployer(
        id="zhipu", name="智谱 Zhipu AI",
        aliases=("zhipu", "zhipu ai", "zhipuai", "智谱", "智谱华章", "智谱ai"),
        careers_url="https://zhipu-ai.jobs.feishu.cn/",         # <title>加入北京智谱华章科技有限公司</title>
    ),
    NotIndexedEmployer(
        id="sensetime", name="商汤科技 SenseTime",
        aliases=("sensetime", "商汤科技", "商汤"),
        # Custom domain. The page <title> was NOT retrieved; what the GET showed is the
        # Feishu Recruitment white label's feishucdn asset fingerprint served from the
        # employer's own host, which is what puts it on this list.
        careers_url="https://hr-jobs.sensetime.com/",
        confirmed_by="feishucdn asset fingerprint on hr-jobs.sensetime.com; title not retrieved",
    ),
    NotIndexedEmployer(
        id="limx", name="逐际动力 LimX Dynamics",
        aliases=("limx", "limx dynamics", "limxdynamics", "逐际动力", "逐际"),
        careers_url="https://career.limxdynamics.com/",         # reports/014: Feishu white label
    ),
    NotIndexedEmployer(
        id="xsquare", name="自变量机器人 X Square Robot",
        aliases=("x square", "xsquare", "x square robot", "x2 robot", "x2-robot",
                 "自变量机器人", "自变量"),
        careers_url="https://x2-robot.jobs.feishu.cn/",         # <title>加入自变量机器人 | 社会招聘</title>
    ),
    NotIndexedEmployer(
        id="spiritai", name="千寻智能 Spirit AI",
        aliases=("spirit ai", "spiritai", "spirit-ai", "千寻智能", "千寻"),
        careers_url="https://nwd4iy9rd2s.jobs.feishu.cn/",      # <title>加入千寻智能（杭州）科技有限公司</title>
    ),
    NotIndexedEmployer(
        id="booster", name="加速进化 Booster Robotics",
        aliases=("booster", "booster robotics", "加速进化"),
        careers_url="https://booster.jobs.feishu.cn/",          # <title>Join Booster Robotics</title>
    ),
    # 2026-10-08 survey (reports/060). Confirmed by <title> on that day.
    NotIndexedEmployer(
        id="noematrix", name="穹彻智能 Noematrix",
        aliases=("noematrix", "穹彻智能", "穹彻"),
        # Its own page (www.noematrix.ai/join-us, <title>加入我们 | 穹彻智能</title>) links to
        # this Feishu tenant, which belongs to 非夕 Flexiv: <title>加入穹彻智能</title>.
        careers_url="https://flexivrobotics.jobs.feishu.cn/971932",
    ),
    NotIndexedEmployer(
        id="engineai", name="众擎机器人 EngineAI",
        aliases=("engineai", "engine ai", "众擎机器人", "众擎"),
        careers_url="https://dx3a2bminsq.jobs.feishu.cn/",      # <title>加入深圳市众擎机器人科技有限公司</title>
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
    ),
)

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
