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

This file is DECLARATIVE. Nothing here is crawled, fetched or inferred at runtime. Every
`careers_url` was confirmed by ONE plain GET of the portal root whose `<title>` names the
employer (reports/014 showed that a 200 alone is not enough: `horizon.jobs.feishu.cn` is a
different company). Where we could not confirm a host, the URL stays None rather than a
guess.

Entries are removed the day an employer becomes indexable (they authorise the scopes, or
move to an ATS that is publicly readable), because `service` consults the live index first
and only falls back to this list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FEISHU_ATS = "feishu"

# One honest sentence, reused verbatim on every Feishu entry so the wording cannot drift.
FEISHU_REASON = (
    "This employer's careers site runs on Feishu Recruitment (飞书招聘), whose job-list API "
    "requires a client-computed request signature; we treat that as access control and do "
    "not work around it, so none of its postings are in this index."
)

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
}


@dataclass(frozen=True)
class NotIndexedEmployer:
    id: str                       # our stable slug, same convention as companies.id
    name: str                     # bilingual display name, as the index would show it
    aliases: tuple[str, ...]      # what a seeker actually types, in either language
    careers_url: str | None       # the employer's own portal; None when unconfirmed
    ats: str = FEISHU_ATS
    reason: str = FEISHU_REASON
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
            "employer_opt_in": dict(self.employer_opt_in),
        }


# Portal roots. Confirmed by <title> on 2026-09-23 unless noted otherwise.
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
        careers_url="https://hr-jobs.sensetime.com/",           # custom domain, Feishu white label
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
)

_BY_ID = {e.id: e for e in NOT_INDEXED}


def _fold(s: str) -> str:
    return " ".join((s or "").casefold().split())


def lookup(query: str) -> list[NotIndexedEmployer]:
    """Resolve what a caller typed against the registry, the way resolve_company does.

    Exact hits on id / name / alias win outright. Otherwise a caseless substring of the
    query inside a name or alias, or of an alias inside the query ("Momenta 招聘"), so a
    seeker who types either half of a bilingual name still lands. Single characters are
    never matched: "a" is not a company.
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
        if any(q in n for n in names) or any(len(n) >= 2 and n in q for n in names):
            out.append(e)
    return out


def by_id(employer_id: str) -> NotIndexedEmployer | None:
    return _BY_ID.get((employer_id or "").strip().casefold())
