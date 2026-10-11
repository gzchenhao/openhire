"""Sanctions screening for `check_employer`, done on the seeker's own machine (reports/070).

Why: when OFAC designated Prince Group on 2025-10-14, eleven of its Hong Kong companies
were live on the Companies Registry. A registration says a company exists; a sanctions
list says who the world has decided not to deal with. They answer different questions, so
the checklist asks both.

How: the OFAC SDN and consolidated (non-SDN) lists are public CSV files with no key. They
are downloaded to OPENHIRE_HOME/sanctions at most once a day (one plain GET per file, the
same client as every other check) and the company's name is compared LOCALLY: no name is
ever sent to a sanctions service. A match is reported as the entry it matched, never as a
verdict: names collide, and the seeker reads the entry.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from pathlib import Path

from .. import config
from . import checks

FILES = {
    "sdn": "https://www.treasury.gov/ofac/downloads/sdn.csv",
    "sdn_alt": "https://www.treasury.gov/ofac/downloads/alt.csv",
    "cons": "https://www.treasury.gov/ofac/downloads/consolidated/cons_prim.csv",
    "cons_alt": "https://www.treasury.gov/ofac/downloads/consolidated/cons_alt.csv",
}
LIST_NAMES = {"sdn": "OFAC SDN", "cons": "OFAC Consolidated (non-SDN)"}
SOURCE = "OFAC SDN + consolidated lists (treasury.gov), downloaded to this machine and matched locally"
TTL = dt.timedelta(hours=24)
MAX_MATCHES = 10

# Legal-form tokens stripped from the END of a name before comparing. Only these: stripping
# "group" or "holdings" would turn Prince Holding Group into "prince" and match the world.
_LEGAL_SUFFIXES = (
    "limited", "ltd", "co", "company", "corp", "corporation", "inc", "incorporated", "llc",
    "plc", "pte", "pty", "sa", "ag", "gmbh", "bv", "nv", "sarl", "srl",
    "有限公司", "股份有限公司", "有限责任公司", "有限責任公司",
)
_PUNCT = re.compile(r"[^\w一-鿿]+")
_CJK = re.compile(r"[一-鿿]")


def normalise(name: str | None) -> str:
    """Lower-case, punctuation to spaces, legal-form suffixes dropped from the end."""
    text = _PUNCT.sub(" ", (name or "").lower()).strip()
    tokens = text.split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    # CJK suffixes are glued to the name: "深圳某某科技有限公司" -> "深圳某某科技".
    out = " ".join(tokens)
    for suf in ("股份有限公司", "有限责任公司", "有限責任公司", "有限公司"):
        if out.endswith(suf):
            out = out[: -len(suf)].strip()
    return out


def name_candidates(name: str, aliases=()) -> set[str]:
    """The spellings to compare: the name, its Latin part, its CJK part, and any aliases."""
    raw = [name, *aliases]
    latin = _CJK.sub(" ", name or "")
    cjk = "".join(ch for ch in (name or "") if _CJK.match(ch))
    raw += [latin, cjk]
    cands = {normalise(x) for x in raw if x}
    return {c for c in cands if len(c) >= 3}


def _cache_dir() -> Path:
    d = config.CLIENT_HOME / "sanctions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_lists(allow_network: bool = True) -> dict | None:
    """The four CSV texts, from the daily cache or one GET each. None when a file is missing
    and could not be fetched; `reason` tells the caller which."""
    cache = _cache_dir()
    now = dt.datetime.now(dt.timezone.utc)
    texts: dict[str, str] = {}
    reason = None
    for key, url in FILES.items():
        path = cache / f"{key}.csv"
        fresh = path.exists() and now - dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc) < TTL
        if not fresh and allow_network:
            r = checks._get(url)
            if r is not None and r.status_code == 200 and r.text.strip():
                path.write_text(r.text, encoding="utf-8")
            elif r is None:
                reason = "network"
            else:
                reason = reason or "http_status"
        if path.exists():
            texts[key] = path.read_text(encoding="utf-8", errors="replace")
        else:
            return {"error": reason or ("offline" if not allow_network else "network")}
    downloaded = min(dt.datetime.fromtimestamp((cache / f"{k}.csv").stat().st_mtime, dt.timezone.utc) for k in FILES)
    return {"texts": texts, "downloaded": downloaded.date().isoformat()}


def _rows(text: str) -> list[list[str]]:
    return [r for r in csv.reader(io.StringIO(text)) if len(r) >= 4]


def entries(lists: dict) -> list[dict]:
    """Every primary and alternate name with its entry number, type, programme and list."""
    out: list[dict] = []
    for key, label in LIST_NAMES.items():
        primaries = {}
        for r in _rows(lists["texts"].get(key, "")):
            ent = r[0].strip()
            primaries[ent] = {"ent_num": ent, "name": r[1].strip(), "type": r[2].strip(), "program": r[3].strip(), "list": label}
            out.append(primaries[ent])
        for r in _rows(lists["texts"].get(key + "_alt", "")):
            ent = r[0].strip()
            p = primaries.get(ent)
            if p and r[3].strip() and r[3].strip() != "-0-":
                out.append({**p, "name": r[3].strip(), "alias_of": p["name"], "alias_type": r[2].strip()})
    return out


def screen(name: str, aliases=(), allow_network: bool = True, lists: dict | None = None) -> dict:
    """Facts: does any OFAC entry share this name? Never a verdict."""
    cands = name_candidates(name, aliases)
    if not cands:
        return {"status": "not_applicable", "note": "没有可比对的公司名", "source": SOURCE, "matches": []}
    data = lists if lists is not None else load_lists(allow_network)
    if not data or "texts" not in data:
        err = (data or {}).get("error", "network")
        note = {
            "offline": "本次不联网，且本机没有名单缓存",
            "http_status": "名单服务器答复了但没有给出文件，本机也没有缓存",
        }.get(err, "本次没有拿到制裁名单（网络不通或超时，且本机没有缓存），说明的是这次查询的网络，不是雇主")
        return {"status": "unavailable", "reason": err, "note": note, "source": SOURCE, "matches": []}
    hits = [e for e in entries(data) if normalise(e["name"]) in cands]
    if hits:
        shown = hits[:MAX_MATCHES]
        desc = "；".join(
            f"{h['name']}（{h['list']}，{h['type'] or '类型未标'}，{h['program']}" + (f"，别名属 {h['alias_of']}" if h.get("alias_of") else "") + "）"
            for h in shown
        )
        return {
            "status": "not_verified",
            "note": f"与 OFAC 名单条目同名：{desc}。同名不等于同一主体，打开名单核对实体编号与地址（名单下载于 {data['downloaded']}）",
            "source": SOURCE, "matches": shown, "downloaded": data["downloaded"],
        }
    return {
        "status": "verified",
        "note": f"OFAC SDN 与综合名单里没有同名条目（名单下载于 {data['downloaded']}）；只比对名称，关联方和其他国家的名单不在比对范围",
        "source": SOURCE, "matches": [], "downloaded": data["downloaded"],
    }
