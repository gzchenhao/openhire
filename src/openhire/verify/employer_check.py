"""The checklist behind `check_employer`: facts, sources, times. Never a verdict.

Howard's framing (reports/065): a seeker asks the assistant "is this company what it says
it is?" and gets a list of checks, each `verified` / `not_verified` / `unavailable` /
`not_applicable` / `pending_user`, each naming its source and when it was checked. The
free checks run here with nothing from the seeker. The ones that cost money (the company
register) run only with the seeker's own key on the seeker's own machine, else they come
back `pending_user` with the ways to get them. There is no composite score and no
"safe / unsafe": a company that fails a check gets the fact stated beside it, and the
sentence at the bottom says what this is and is not.
"""

from __future__ import annotations

import datetime as dt
from typing import Callable

from . import checks, org_events, sanctions, tianyancha

NOT_A_VERDICT = (
    "These are facts with sources and times, not a judgement of the employer. A company "
    "can fail a check and be fine (a new domain, an overseas site with no ICP record) or "
    "pass every check and still waste your time. Read the items, not a total."
)

AIQICHA = "https://aiqicha.baidu.com/s?q={name}"
GSXT = "https://www.gsxt.gov.cn/"
MIIT_ICP = "https://beian.miit.gov.cn/"
# Hong Kong and overseas employers are not in the mainland register at all (reports/068):
# the HK Companies Registry's e-Services Portal (company name search is free, no account),
# the HK Police Scameter (a phone number, URL, email or receiving account against the
# police scam database), and OpenCorporates for most other jurisdictions.
HK_CR_ESERVICES = "https://www.e-services.cr.gov.hk/"
HK_SCAMETER = "https://cyberdefender.hk/scameter/"
OPENCORPORATES = "https://opencorporates.com/companies?q={name}"
CHECKLIST_URL = "https://gzchenhao.github.io/openhire/checklist.html"
CHECKLIST_URL_CN = "https://openhire-vlny.onrender.com/checklist"  # the same page, for mainland China


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _item(check_id: str, label: str, status: str, note: str, *, source: str, **extra) -> dict:
    out = {"id": check_id, "label": label, "status": status, "note": note, "source": source, "checked_at": _now()}
    out.update(extra)
    return out


def text_scan_items(message_text: str | None = None, posting_text: str | None = None) -> list[dict]:
    """The checks that read only text the user supplied: a pasted private message, and the
    outsourcing words in either text. Pure, no network, nothing kept (reports/108)."""
    out = []
    if message_text:
        flags = checks.message_red_flags_in(message_text)
        out.append(_item(
            "message_red_flags", "对方发来的文字里的骗局特征", "not_verified" if flags else "verified",
            ("出现了：" + "、".join(flags) + "。这些是冒充用人方的骗局常用的说法；先按查公司页把公司全称查一遍，"
             "不交任何费用、不装对方指定的软件、不共享屏幕、不在聊天里发证件照和验证码") if flags
            else "没有出现交费、加微信、装软件、共享屏幕、贷款这类说法；这只说明这段文字里没有，不说明对方可信",
            source="OpenHire message red-flag list (reports/108), matched on this machine", flags=flags))
    words = checks.outsourcing_words_in(message_text, posting_text)
    if message_text or posting_text:
        out.append(_item(
            "outsourcing_words", "外包、劳务派遣的字样", "pending_user" if words else "not_applicable",
            ("出现了：" + "、".join(words) + "。合同可能和另一家公司签（外包或派遣公司），你真正的雇主是那一家："
             "问清合同主体全称，按查公司页把那家也查一遍；劳务派遣公司要有劳务派遣经营许可证。这只是字样，不是结论") if words
            else "没有出现外包、劳务派遣、驻场这类字样",
            source="OpenHire outsourcing word list (reports/108)", words=words))
    return out


def build_checklist(
    *,
    query: dict,
    index_facts: dict | None,
    known_not_indexed: dict | None,
    domain: str | None,
    posting_text: str | None = None,
    message_text: str | None = None,
    run_network: bool = True,
    homepage_fn: Callable[..., dict] | None = None,
    domain_age_fn: Callable[[str], dict] | None = None,
    wayback_fn: Callable[[str], dict] | None = None,
    register_fn: Callable[[str], dict] | None = None,
    sanctions_fn: Callable[..., dict] | None = None,
    org_events_fn: Callable[..., dict] | None = None,
) -> dict:
    """Assemble the checklist. Network functions are injectable so tests stay hermetic;
    the defaults are looked up at call time so a monkeypatched module attribute is seen."""
    homepage_fn = homepage_fn or checks.homepage_check
    domain_age_fn = domain_age_fn or checks.domain_age
    wayback_fn = wayback_fn or checks.wayback_first_capture
    register_fn = register_fn or tianyancha.fetch_baseinfo
    sanctions_fn = sanctions_fn or sanctions.screen
    org_events_fn = org_events_fn or org_events.screen
    items: list[dict] = []
    pending: list[dict] = []
    name = (index_facts or {}).get("company") or (known_not_indexed or {}).get("name") or query.get("company")

    # 1. Our own index: what the employer's own system shows, with its date semantics.
    if index_facts:
        src = "OpenHire index (the employer's own system)"
        if index_facts.get("date_source") == "employer_self_reported":
            src = "OpenHire index (a roster the employer reported itself, marked as such)"
        note = (f"在架 {index_facts.get('active_jobs')} 个岗位，在架中位 {index_facts.get('median_days_open')} 天；"
                f"发布日由{'雇主自报' if index_facts.get('date_source') == 'employer_self_reported' else ('雇主系统写入' if index_facts.get('posting_dates_reported') else '我们首次抓到的时间代替（来源不给日期）')}")
        if index_facts.get("claimed"):
            note += f"；雇主已认领（{(index_facts.get('claimed_at') or '')[:10]}）"
        items.append(_item("in_index", "在我们索引里（雇主自己的系统）", "verified", note, source=src,
                           active_jobs=index_facts.get("active_jobs"), median_days_open=index_facts.get("median_days_open"),
                           posting_dates_reported=index_facts.get("posting_dates_reported"),
                           date_source=index_facts.get("date_source"), claimed=index_facts.get("claimed"),
                           index_built_at=index_facts.get("index_built_at")))
    elif known_not_indexed:
        ats = known_not_indexed.get("ats") or ""
        if "ceased" in ats:
            items.append(_item("ceased_operations", "公司状态", "verified", known_not_indexed.get("reason_zh") or known_not_indexed.get("reason") or "",
                               source="OpenHire registry (dated public facts)", details=known_not_indexed.get("reason")))
        else:
            items.append(_item("known_not_indexed", "在我们索引里", "not_applicable",
                               f"我们知道这家公司但没有收录：{known_not_indexed.get('reason_zh') or ''}",
                               source="OpenHire registry", careers_url=known_not_indexed.get("careers_url"),
                               employer_opt_in=known_not_indexed.get("employer_opt_in")))
    else:
        items.append(_item("in_index", "在我们索引里", "not_verified",
                           "不在索引里：它可能不用我们能读的招聘系统，也可能不在我们的三个方向里；这不说明它有问题",
                           source="OpenHire index"))

    ceased = any(i["id"] == "ceased_operations" for i in items)

    # 2. The employer's own domain: age, history, ICP record on its homepage.
    if ceased:
        items.append(_item("domain", "官网域名", "not_applicable", "公司已停止运营，域名检查无意义", source="OpenHire registry"))
    elif not domain:
        items.append(_item("domain", "官网域名", "not_applicable",
                           "没有这家公司自己的域名可查：招聘页托管在招聘系统的域名上。把官网域名作为 domain 参数传进来可以补查",
                           source="n/a"))
    elif not run_network:
        items.append(_item("domain", "官网域名", "unavailable", "本次没有联网检查", source="n/a", domain=domain))
    else:
        # `reason` tells "we could not reach the source" (network) apart from "the source
        # answered and has no record"; the first says nothing about the employer.
        age = domain_age_fn(domain)
        items.append(_item("domain_age", "域名注册日期", age.get("status", "unavailable"), age.get("note", ""),
                           source="RDAP (the registry's own record)", domain=domain,
                           registered=age.get("registered"), age_days=age.get("age_days"), reason=age.get("reason")))
        hist = wayback_fn(domain)
        items.append(_item("site_history", "网站历史", hist.get("status", "unavailable"), hist.get("note", ""),
                           source="Internet Archive Wayback Machine", first_capture=hist.get("first_capture"),
                           reason=hist.get("reason")))
        home = homepage_fn(domain, None, name)
        items.append(_item("icp_on_homepage", "首页备案号", home.get("status", "unavailable"), home.get("note", ""),
                           source=f"https://{domain}/ (one GET)", icp_on_page=home.get("icp_on_page", []),
                           reason=home.get("reason")))

    # 3. The posting the seeker is looking at, if they pasted it.
    if posting_text:
        flags = checks.red_flags_in(posting_text)
        items.append(_item("posting_red_flags", "岗位文本里的骗局招聘特征", "not_verified" if flags else "verified",
                           ("命中：" + "、".join(flags) + "。这些词在真实的智驾 / 具身 / AI 基础设施岗位里几乎不会出现") if flags
                           else "没有命中境外高薪、包机票、不限经验、打字员这类特征词",
                           source="OpenHire red-flag list (reports/064)", flags=flags))
    items.extend(text_scan_items(message_text=message_text, posting_text=posting_text))

    # 3b. Sanctions lists, matched on this machine (reports/070): a live registration proved
    # nothing about Prince Group's eleven Hong Kong companies; the OFAC designation did.
    if ceased:
        items.append(_item("sanctions_screen", "制裁名单", "not_applicable", "公司已停止运营", source="n/a"))
    elif not name:
        items.append(_item("sanctions_screen", "制裁名单", "not_applicable", "没有公司名可比对", source="n/a"))
    else:
        s = sanctions_fn(name, aliases=(), allow_network=run_network)
        items.append(_item("sanctions_screen", "制裁名单（OFAC SDN 与综合名单，下载到本机后本机比对）",
                           s.get("status", "unavailable"), s.get("note", ""),
                           source=s.get("source", sanctions.SOURCE), matches=s.get("matches", []),
                           reason=s.get("reason"), lists_downloaded=s.get("downloaded")))

    # 3c. Organisational events on public record (reports/077): EarlyTip's export, read
    # whole to this machine once a day and matched here by its published company_key.
    # Type, date, domain and link only; never the headline. A ceased employer still gets
    # it: the bankruptcy may be exactly the event on record.
    if not name:
        items.append(_item("org_events", "组织变化与融资并购事件", "not_applicable", "没有公司名可比对", source="n/a"))
    else:
        aliases = tuple((known_not_indexed or {}).get("aliases") or ())
        o = org_events_fn(name, aliases=aliases, allow_network=run_network)
        items.append(_item("org_events", "组织变化与融资并购事件（EarlyTip 公开索引，下载到本机后本机比对）",
                           o.get("status", "unavailable"), o.get("note", ""),
                           source=o.get("source", org_events.SOURCE), events=o.get("events", []), total=o.get("total", 0),
                           reason=o.get("reason"), file_generated_at=o.get("generated_at"), file_downloaded=o.get("downloaded")))

    # 4. The company register: the seeker's own key, or the ways to get it.
    if ceased:
        items.append(_item("registry_record", "工商登记", "not_applicable", "公司已停止运营", source="n/a"))
    elif not name:
        items.append(_item("registry_record", "工商登记", "not_applicable", "没有公司名可查", source="n/a"))
    else:
        reg = register_fn(name) if run_network else {"status": "unavailable", "note": "本次没有联网检查"}
        status = reg.get("status", "unavailable")
        item = _item("registry_record", "工商登记（成立日期、经营状态、参保人数）", status, reg.get("note", ""),
                     source=reg.get("source", "天眼查 OpenAPI（需要你自己的 key）"), record=reg.get("record"),
                     reason=reg.get("reason"))
        items.append(item)
        if status == "pending_user":
            pending.append({
                "id": "registry_record",
                "label": "工商登记（成立日期、经营状态、注册资本、参保人数、法定代表人）",
                "why_pending": "政府公示系统有验证码，没有接口；天眼查有接口但按次收费，钱由你自己付，key 只放在你自己的电脑上，我们看不到",
                "how": [
                    {"way": "tianyancha_key", "steps": "到 open.tianyancha.com 注册并充值，拿到 API key，在运行 OpenHire 的环境里设置 TIANYANCHA_API_KEY，再问一次；每次查询由天眼查从你的账户扣费"},
                    {"way": "tianyancha_mcp", "steps": "如果你的助手已经接了天眼查自己的 MCP 服务（天眼 AI，用你自己的账号，个人免费账号也能查工商登记，以天眼查页面为准，入口 ai.tianyancha.com），让它查这家公司的工商登记：" + str(name) + "。天眼查不支持中国大陆、港澳台以外的用户和 IP"},
                    {"way": "manual_free", "steps": f"免费手动：爱企查 {AIQICHA.format(name=name)} ，或国家企业信用信息公示系统 {GSXT}（按全称查，有验证码）"},
                    {"way": "manual_free_hk_overseas",
                     "steps": (f"香港公司：公司註冊處電子服務網站 {HK_CR_ESERVICES} 免费查公司名称（无需账户）；"
                               f"招聘方留的电话、网址、邮箱或收款账户可在香港警务处防騙視伏器 {HK_SCAMETER} 查；"
                               f"其他境外公司：OpenCorporates {OPENCORPORATES.format(name=name)} 。"
                               "任何要你先出境面试、先付费、先交护照的招聘，先停下来查")},
                ],
            })

    return {
        "@type": "EmployerCheck",
        "query": query,
        "company": name,
        "domain": domain,
        "checks": items,
        "pending_user": pending,
        "summary": {
            "verified": sum(1 for i in items if i["status"] == "verified"),
            "not_verified": sum(1 for i in items if i["status"] == "not_verified"),
            "unavailable": sum(1 for i in items if i["status"] == "unavailable"),
            "not_applicable": sum(1 for i in items if i["status"] == "not_applicable"),
            "pending_user": sum(1 for i in items if i["status"] == "pending_user"),
        },
        "not_a_verdict": NOT_A_VERDICT,
        "checklist_url": CHECKLIST_URL,
        "checklist_url_cn": CHECKLIST_URL_CN,
        "checklist_note": "求职清单（找工作每一步该做什么、OpenHire 替你做哪些、其余去哪里做，含反诈骗步骤）："
                          "找工作的人第一次用，先把这页给他。The job-search checklist, with the anti-scam steps.",
        "privacy": "This check sent the company's name or domain to RDAP, the Internet Archive and the company's own site, "
                   "and to 天眼查 only if you set your own key. The OFAC lists and the EarlyTip events file were downloaded "
                   "whole and matched on this machine, so neither learned the name. Nothing about you was sent anywhere.",
        "checked_at": _now(),
    }
