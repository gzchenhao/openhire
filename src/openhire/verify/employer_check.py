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

from . import checks, tianyancha

NOT_A_VERDICT = (
    "These are facts with sources and times, not a judgement of the employer. A company "
    "can fail a check and be fine (a new domain, an overseas site with no ICP record) or "
    "pass every check and still waste your time. Read the items, not a total."
)

AIQICHA = "https://aiqicha.baidu.com/s?q={name}"
GSXT = "https://www.gsxt.gov.cn/"
MIIT_ICP = "https://beian.miit.gov.cn/"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _item(check_id: str, label: str, status: str, note: str, *, source: str, **extra) -> dict:
    out = {"id": check_id, "label": label, "status": status, "note": note, "source": source, "checked_at": _now()}
    out.update(extra)
    return out


def build_checklist(
    *,
    query: dict,
    index_facts: dict | None,
    known_not_indexed: dict | None,
    domain: str | None,
    posting_text: str | None = None,
    run_network: bool = True,
    homepage_fn: Callable[..., dict] | None = None,
    domain_age_fn: Callable[[str], dict] | None = None,
    wayback_fn: Callable[[str], dict] | None = None,
    register_fn: Callable[[str], dict] | None = None,
) -> dict:
    """Assemble the checklist. Network functions are injectable so tests stay hermetic;
    the defaults are looked up at call time so a monkeypatched module attribute is seen."""
    homepage_fn = homepage_fn or checks.homepage_check
    domain_age_fn = domain_age_fn or checks.domain_age
    wayback_fn = wayback_fn or checks.wayback_first_capture
    register_fn = register_fn or tianyancha.fetch_baseinfo
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
        age = domain_age_fn(domain)
        items.append(_item("domain_age", "域名注册日期", age.get("status", "unavailable"), age.get("note", ""),
                           source="RDAP (the registry's own record)", domain=domain,
                           registered=age.get("registered"), age_days=age.get("age_days")))
        hist = wayback_fn(domain)
        items.append(_item("site_history", "网站历史", hist.get("status", "unavailable"), hist.get("note", ""),
                           source="Internet Archive Wayback Machine", first_capture=hist.get("first_capture")))
        home = homepage_fn(domain, None, name)
        items.append(_item("icp_on_homepage", "首页备案号", home.get("status", "unavailable"), home.get("note", ""),
                           source=f"https://{domain}/ (one GET)", icp_on_page=home.get("icp_on_page", [])))

    # 3. The posting the seeker is looking at, if they pasted it.
    if posting_text:
        flags = checks.red_flags_in(posting_text)
        items.append(_item("posting_red_flags", "岗位文本里的骗局招聘特征", "not_verified" if flags else "verified",
                           ("命中：" + "、".join(flags) + "。这些词在真实的智驾 / 具身 / AI 基础设施岗位里几乎不会出现") if flags
                           else "没有命中境外高薪、包机票、不限经验、打字员这类特征词",
                           source="OpenHire red-flag list (reports/064)", flags=flags))

    # 4. The company register: the seeker's own key, or the ways to get it.
    if ceased:
        items.append(_item("registry_record", "工商登记", "not_applicable", "公司已停止运营", source="n/a"))
    elif not name:
        items.append(_item("registry_record", "工商登记", "not_applicable", "没有公司名可查", source="n/a"))
    else:
        reg = register_fn(name) if run_network else {"status": "unavailable", "note": "本次没有联网检查"}
        status = reg.get("status", "unavailable")
        item = _item("registry_record", "工商登记（成立日期、经营状态、参保人数）", status, reg.get("note", ""),
                     source=reg.get("source", "天眼查 OpenAPI（需要你自己的 key）"), record=reg.get("record"))
        items.append(item)
        if status == "pending_user":
            pending.append({
                "id": "registry_record",
                "label": "工商登记（成立日期、经营状态、注册资本、参保人数、法定代表人）",
                "why_pending": "政府公示系统有验证码，没有接口；天眼查有接口但按次收费，钱由你自己付，key 只放在你自己的电脑上，我们看不到",
                "how": [
                    {"way": "tianyancha_key", "steps": "到 open.tianyancha.com 注册并充值，拿到 API key，在运行 OpenHire 的环境里设置 TIANYANCHA_API_KEY，再问一次；每次查询由天眼查从你的账户扣费"},
                    {"way": "tianyancha_mcp", "steps": "如果你的助手已经接了天眼查 MCP（https://mcp.tianyancha.com/v1，你自己的 key），让它查这家公司的基本信息：" + str(name)},
                    {"way": "manual_free", "steps": f"免费手动：爱企查 {AIQICHA.format(name=name)} ，或国家企业信用信息公示系统 {GSXT}（按全称查，有验证码）"},
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
        "privacy": "This check sent the company's name or domain to RDAP, the Internet Archive and the company's own site, "
                   "and to 天眼查 only if you set your own key. Nothing about you was sent anywhere.",
        "checked_at": _now(),
    }
