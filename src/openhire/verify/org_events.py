"""Organisational events from the EarlyTip public export, for `check_employer`.

EarlyTip (earlytip.com) publishes one JSON file of organisational and financing events it
has indexed (executive departures, restructurings, funding rounds, acquisitions,
bankruptcies, new companies) for the same sectors this index covers. OpenHire is the
consumer side only (the producer's spec, "org_events 预登记 v2", is theirs): this module
reads the file and hangs its events on an employer, and the rules of what to show are
fixed here, not negotiated per call.

How it reads (D8 of the spec): one plain GET of the whole public file to the seeker's own
machine, at most once a day, cached under OPENHIRE_HOME/earlytip. The server never learns
which company the seeker asked about, and nothing about the seeker is sent.

What it shows, per event: the event type as the export labels it, one date (the event's
own date when the export has it, else the day EarlyTip published it), the amount where the
export carries one (verbatim from EarlyTip's own headline or summary, its D3 rule; shown
since 0.8.9 by Howard's ruling of 2026-10-14), the source domain and a plain link to the
source page. Never the headline and never EarlyTip's summary: the
source sites' terms govern copying, a plain link is a pointer. Where a site's terms list
"linking" itself among the prohibited acts (reports/077), no link either, only the
domain. Retracted events are dropped, an event whose company the export could not name is
skipped, and an event the export marks unverified says so.

Matching: the export carries `company_key`, a published normalisation; the same algorithm
is implemented here (`company_key`) and applied to every spelling this index holds for the
employer (the bilingual display name, each half of it, the registry aliases). An employer
is matched as the event's subject (`company`) or as its counterparty
(`related_companies`), and the item says which. The export's own names are split the same
way before keying, since 0.8.10: its first version wrote 庞伯特Pongbot as one word.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from .. import config
from . import checks

URL = "https://earlytip.com/data/org_events.json"
SOURCE = "EarlyTip org_events export (earlytip.com, public file downloaded to this machine; matched locally)"
SCHEMA_VERSION = 1
TTL = dt.timedelta(hours=24)
MAX_SHOWN = 20
# The export is produced by EarlyTip; what it checked its values against is its own
# published headline and summary, not the source article. Said as-is, every time.
PROVENANCE = (
    "据 EarlyTip 整理的公开事件索引：公司名、金额、日期只与 EarlyTip 自己发布的标题和推荐理由核对过，"
    "没有和来源正文逐字核对；这里只转事件类型、日期、金额、来源域名和链接，不转标题"
)
# Sites whose terms list "linking" itself among the prohibited acts (cs.com.cn, bloomberg,
# reuters from the first round; sina 8.4 and 财联社 8.2.3 quoted in reports/077). For these
# the item carries the domain and no URL. Subdomains count: t.cj.sina.com.cn is sina.
NO_LINK_DOMAINS = ("cs.com.cn", "bloomberg.com", "reuters.com", "sina.com.cn", "chinastarmarket.cn", "cls.cn")
# The 18 keys every event must carry (spec 一.2); a file missing one is not this schema.
EVENT_KEYS = (
    "event_id", "company", "company_key", "company_aliases", "related_companies", "event_type",
    "event_date", "published_date", "amount", "title", "url", "source", "unverified",
    "captured_at", "backfilled", "retracted", "retracted_at", "retraction_reason",
)
# Must never be in the export (spec 一.2 "明确不含"): the summary is EarlyTip's own text.
FORBIDDEN_KEYS = ("why", "critic", "cat")
# The published blackout: no event may be dated to these days (spec 四.C.1, 六.b).
BLACKOUT = (dt.date(2026, 9, 29), dt.date(2026, 10, 3))
# Financing events have no counterparty by rule (D10): a non-empty related_companies there
# is a producer-side slip the audit reports.
FUNDING_TYPES = ("融资进展", "融资带来组织变化")

_LATIN_SUFFIXES = ("inc", "incorporated", "ltd", "limited", "llc", "corp", "corporation", "co", "gmbh", "ag", "plc", "sa")
_CJK_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司", "集团", "公司")  # longest first, as the rule says
_WORD_SPLIT = re.compile(r"[\s\W_]+", re.UNICODE)
_CJK = re.compile(r"[一-鿿]")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --- the published key, reimplemented verbatim (spec 二.1) --------------------------------
def company_key(name: str | None) -> str:
    """NFKC + casefold; Latin legal-form words stripped from the end; every separator,
    punctuation, symbol and control character removed; Chinese legal-form suffixes
    stripped from the end, longest match first. Empty means no key (the producer refuses
    to publish such a row; the reader simply cannot match it)."""
    text = unicodedata.normalize("NFKC", name or "").casefold()
    tokens = [t for t in _WORD_SPLIT.split(text) if t]
    while tokens and tokens[-1] in _LATIN_SUFFIXES:
        tokens.pop()
    text = " ".join(tokens)
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] not in "ZPS" and unicodedata.category(ch) != "Cc")
    changed = True
    while changed:
        changed = False
        for suf in _CJK_SUFFIXES:
            if text.endswith(suf):
                text = text[: -len(suf)]
                changed = True
                break
    return text


def event_id(url: str | None, title: str | None) -> str:
    """sha256(url without surrounding space or #fragment + "\\n" + title without
    surrounding space or the 待核实 marker), first 16 hex digits (spec 一.2)."""
    u = (url or "").strip().split("#", 1)[0]
    t = (title or "").strip().replace("（待核实）", "").replace("(待核实)", "")
    return hashlib.sha256((u + "\n" + t).encode("utf-8")).hexdigest()[:16]


def name_variants(name: str | None, aliases=()) -> list[str]:
    """Every spelling worth keying: the name, its Latin half, its CJK half, the aliases."""
    out: list[str] = []
    for raw in (name, *aliases):
        if not raw:
            continue
        latin = _CJK.sub(" ", raw).strip()
        cjk = "".join(ch for ch in raw if _CJK.match(ch))
        for v in (raw, latin, cjk):
            v = v.strip()
            if v and v not in out:
                out.append(v)
    return out


def link_allowed(source: str | None) -> bool:
    host = checks.normalise_domain(source)
    return bool(host) and not any(host == d or host.endswith("." + d) for d in NO_LINK_DOMAINS)


# --- the file: one GET a day, cached ------------------------------------------------------
def _cache_path() -> Path:
    d = config.CLIENT_HOME / "earlytip"
    d.mkdir(parents=True, exist_ok=True)
    return d / "org_events.json"


def parse(text: str) -> dict:
    """The file as a dict, or {"error": ...} naming what is wrong with it. A file of
    another schema version is refused whole: its keys may mean something else."""
    try:
        data = json.loads(text)
    except ValueError:
        return {"error": "not_json"}
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return {"error": "not_the_export"}
    if data.get("schema_version") != SCHEMA_VERSION:
        return {"error": "schema_version", "schema_version": data.get("schema_version")}
    return data


def load(allow_network: bool = True, now: dt.datetime | None = None) -> dict:
    """The export from the daily cache or one GET. On failure {"error": reason} where
    `network` means this machine did not reach earlytip.com and says nothing about the data."""
    now = now or dt.datetime.now(dt.timezone.utc)
    path = _cache_path()
    fresh = path.exists() and now - dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc) < TTL
    reason = None
    if not fresh and allow_network:
        r = checks._get(URL)
        if r is None:
            reason = "network"
        elif r.status_code != 200 or not r.text.strip():
            reason = "http_status"
        else:
            parsed = parse(r.text)
            if "error" in parsed:
                reason = parsed["error"]
            else:
                path.write_text(r.text, encoding="utf-8")
    if not path.exists():
        return {"error": reason or ("offline" if not allow_network else "network")}
    data = parse(path.read_text(encoding="utf-8"))
    if "error" in data:
        return data
    data["downloaded"] = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).date().isoformat()
    return data


# --- matching and the shown shape --------------------------------------------------------
def events_for(data: dict, name: str | None, aliases=()) -> list[dict]:
    """Events whose subject or counterparty keys to any spelling of this employer, newest
    first. Retracted events and events with no company are left out by rule."""
    keys = {company_key(v) for v in name_variants(name, aliases)} - {""}
    if not keys:
        return []
    out = []
    for ev in data.get("events", []):
        if not isinstance(ev, dict) or ev.get("retracted") or not ev.get("company"):
            continue
        subject_keys = {ev.get("company_key") or company_key(ev.get("company"))}
        # The export's own spelling can glue two scripts into one word (庞伯特Pongbot in the
        # first export, reports/077 §9): each script half of its company, alias and
        # counterparty names keys as well, so a seeker's 庞伯特 or Pongbot both land.
        aliases = [a for a in (ev.get("company_aliases") or []) if isinstance(a, str)]
        subject_keys |= {company_key(v) for v in name_variants(ev.get("company"), aliases)}
        related = {company_key(v) for c in (ev.get("related_companies") or []) if isinstance(c, str) for v in name_variants(c)}
        subject_keys.discard("")
        related.discard("")
        if keys & subject_keys:
            role = "subject"
        elif keys & related:
            role = "counterparty"
        else:
            continue
        out.append(present(ev, role))
    out.sort(key=lambda e: (e["date"] or "", e["event_id"]), reverse=True)
    return out


def present(ev: dict, role: str) -> dict:
    """The shown shape: type, one date, domain, link (or none, by domain), flags. No title."""
    source = ev.get("source") or checks.normalise_domain(ev.get("url"))
    allowed = link_allowed(source)
    date = ev.get("event_date") or ev.get("published_date")
    return {
        "event_id": ev.get("event_id"),
        "event_type": ev.get("event_type"),
        "date": date,
        "date_kind": "event_date" if ev.get("event_date") else "published_date",
        "role": role,
        "company": ev.get("company"),
        "related_companies": [c for c in (ev.get("related_companies") or []) if isinstance(c, str)],
        "amount": ev.get("amount") if isinstance(ev.get("amount"), str) and ev.get("amount") else None,
        "source": source,
        "url": ev.get("url") if allowed else None,
        "link_withheld": None if allowed else "该站条款把「链接」本身列为禁止行为，只给域名，见原文",
        "unverified": bool(ev.get("unverified")),
        "backfilled": bool(ev.get("backfilled")),
    }


def screen(name: str | None, aliases=(), allow_network: bool = True, data: dict | None = None) -> dict:
    """The checklist item: what the export holds about this employer, or why it could not
    be read. Facts and pointers, never a verdict on the employer."""
    data = data if data is not None else load(allow_network)
    if "error" in data:
        err = data["error"]
        note = {
            "offline": "本次不联网，且本机没有事件文件缓存",
            "http_status": "earlytip.com 答复了但没有给出文件，本机也没有缓存",
            "schema_version": f"事件文件的 schema_version 是 {data.get('schema_version')}，这个版本的 OpenHire 只读 {SCHEMA_VERSION}；升级 OpenHire 或等下一版",
            "not_json": "事件文件不是合法 JSON，本机也没有可用缓存",
            "not_the_export": "earlytip.com 给出的文件不是事件导出，本机也没有可用缓存",
        }.get(err, "本次没有拿到事件文件（网络不通或超时，且本机没有缓存），说明的是这次查询的网络，不是雇主")
        return {"status": "unavailable", "reason": err, "note": note, "source": SOURCE, "events": [], "total": 0}
    if not name:
        return {"status": "not_applicable", "note": "没有公司名可比对", "source": SOURCE, "events": [], "total": 0}
    found = events_for(data, name, aliases)
    stamp = f"文件生成于 {(data.get('generated_at') or '')[:10]}，下载于 {data.get('downloaded')}，共 {data.get('event_count')} 条"
    if not found:
        # The source answered and holds no record: `unavailable` + `no_record`, the same
        # words RDAP gets, because an absence here says nothing about the employer.
        return {"status": "unavailable", "reason": "no_record",
                "note": f"EarlyTip 的事件索引里没有这家公司的条目（{stamp}）；它只收录 2026-09-20 起的组织变化与融资并购事件，没有条目不说明任何事",
                "source": SOURCE, "events": [], "total": 0, "generated_at": data.get("generated_at"), "downloaded": data.get("downloaded")}
    shown = found[:MAX_SHOWN]
    counts = Counter(e["event_type"] for e in found)
    desc = "；".join(
        f"{e['date'] or '日期未知'} {e['event_type']}" + (f"（{e['amount']}）" if e.get("amount") else "")
        + ("（作为另一方）" if e["role"] == "counterparty" else "")
        + ("（待核实）" if e["unverified"] else "") + f" 来源 {e['source'] or '未知'}"
        for e in shown[:5]
    )
    return {
        "status": "verified",
        "note": f"EarlyTip 收录了 {len(found)} 条与这家公司有关的事件（" + "、".join(f"{t} {n}" for t, n in counts.most_common()) + f"）：{desc}"
                + (f"……共 {len(found)} 条，前 {len(shown)} 条在 events 里" if len(found) > len(shown) else "")
                + f"。{PROVENANCE}（{stamp}）",
        "source": SOURCE, "events": shown, "total": len(found),
        "generated_at": data.get("generated_at"), "downloaded": data.get("downloaded"),
    }


# --- the consumer-side audit (spec 六, the parts a reader can check) ----------------------
def audit(data: dict) -> dict:
    """Check the file against the published spec from the reader's side: shape, keys,
    ids and keys recomputed, dates, the blackout, D10. Returns counts and the offending
    event ids, never fixes anything: findings go back to the producer as rulings."""
    events = [e for e in data.get("events", []) if isinstance(e, dict)]
    problems: dict[str, list[str]] = {}

    def flag(kind: str, ev: dict) -> None:
        problems.setdefault(kind, []).append(str(ev.get("event_id")))

    ids = Counter(str(e.get("event_id")) for e in events)
    for ev in events:
        missing = [k for k in EVENT_KEYS if k not in ev]
        if missing:
            flag("missing_keys", ev)
        if any(k in ev for k in FORBIDDEN_KEYS):
            flag("forbidden_keys", ev)
        if ev.get("event_id") != event_id(ev.get("url"), ev.get("title")):
            flag("event_id_mismatch", ev)
        if ids[str(ev.get("event_id"))] > 1:
            flag("event_id_duplicate", ev)
        if ev.get("company") is not None and ev.get("company_key") != company_key(ev.get("company")):
            flag("company_key_mismatch", ev)
        if ev.get("company") and ("（" in ev["company"] or "(" in ev["company"]):
            flag("company_has_brackets", ev)
        if not ev.get("company"):
            flag("company_null", ev)
        for key in ("event_date", "published_date"):
            v = ev.get(key)
            if v is not None and not (isinstance(v, str) and _DATE.match(v)):
                flag(f"{key}_format", ev)
        pub = ev.get("published_date")
        if isinstance(pub, str) and _DATE.match(pub) and BLACKOUT[0] <= dt.date.fromisoformat(pub) <= BLACKOUT[1]:
            flag("published_in_blackout", ev)
        if ev.get("source") != checks.normalise_domain(ev.get("url")):
            flag("source_mismatch", ev)
        # One direction only: a row can be confirmed later (unverified flips to false, the
        # title keeps its first wording, spec 三.3), but `unverified: true` needs the marker.
        marker = "（待核实）" in (ev.get("title") or "") or "(待核实)" in (ev.get("title") or "")
        if ev.get("unverified") and not marker:
            flag("unverified_without_marker", ev)
        if ev.get("event_type") in FUNDING_TYPES and ev.get("related_companies"):
            flag("funding_with_related", ev)
        if ev.get("retracted") and not ev.get("retracted_at"):
            flag("retracted_without_time", ev)
        # D3 says every amount and date appears in the title or the summary; only the title
        # is exported, so these two are coverage figures, not failures.
        title = ev.get("title") or ""
        if ev.get("amount") and str(ev["amount"]) not in title:
            flag("amount_not_in_title", ev)
        if isinstance(ev.get("event_date"), str) and _DATE.match(ev["event_date"]):
            y, m, d = (int(x) for x in ev["event_date"].split("-"))
            if not any(s in title for s in (ev["event_date"], f"{y}/{m}/{d}", f"{y}年{m}月{d}日")):
                flag("event_date_not_in_title", ev)

    key_to_company: dict[str, set[str]] = {}
    for ev in events:
        if ev.get("company_key") and ev.get("company"):
            key_to_company.setdefault(ev["company_key"], set()).add(ev["company"])
    return {
        "schema_version": data.get("schema_version"),
        "generated_at": data.get("generated_at"),
        "event_count_declared": data.get("event_count"),
        "event_count_actual": len(events),
        "count_matches": data.get("event_count") == len(events),
        "retracted": sum(1 for e in events if e.get("retracted")),
        "backfilled": sum(1 for e in events if e.get("backfilled")),
        "unverified": sum(1 for e in events if e.get("unverified")),
        "company_null": sum(1 for e in events if not e.get("company")),
        "with_event_date": sum(1 for e in events if e.get("event_date")),
        "with_amount": sum(1 for e in events if e.get("amount")),
        "with_related": sum(1 for e in events if e.get("related_companies")),
        "event_types": dict(Counter(str(e.get("event_type")) for e in events).most_common()),
        "sources": dict(Counter(str(e.get("source")) for e in events).most_common()),
        "no_link_sources": dict(Counter(str(e.get("source")) for e in events if not link_allowed(e.get("source"))).most_common()),
        "published_range": [min((e.get("published_date") or "" for e in events), default=None) or None,
                            max((e.get("published_date") or "" for e in events), default=None) or None],
        "companies": sorted({e["company"] for e in events if e.get("company")}),
        "keys_with_two_companies": {k: sorted(v) for k, v in key_to_company.items() if len(v) > 1},
        "problems": problems,
        "problem_count": sum(len(v) for k, v in problems.items() if not k.endswith("_not_in_title") and k != "company_null"),
    }
