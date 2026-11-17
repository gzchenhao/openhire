"""Which sector each indexed employer is in, so a seeker can say "autonomous-driving companies
only" (persona test, 2026-10-30: four of ten simulated seekers asked for exactly that and the
assistant had to search employer by employer; reports/107).

One label per employer, from what the company makes, the same four words everywhere:
  autonomous_driving  self-driving and driver assistance, the lidar / chips / trucks / cars
                      built for it, and autonomy off the road (drones, ships, airport tugs)
  embodied_ai         robots: humanoids, arms, mobile and warehouse robots, robot foundation models
  ai_infra            AI labs and models, AI chips and compute, AI developer tools and AI-first apps
  finance             banks, brokers, insurers, asset managers and trading firms; so far their
                      Hong Kong postings only (reports/151), middle and back office included
  other               everything else the index carries (cloud software, fintech, consumer)

The first three match not_indexed.SECTORS, so list_portals and search_jobs mean the same thing
by a sector. A board the user added on their own machine has no label (sector_of returns None)
and is left out of a sector search rather than guessed. tests/test_sectors.py keeps every
seeded employer labelled: a new seed row without a sector here fails the suite.
"""

from __future__ import annotations

from .not_indexed import SECTOR_ALIASES as _PORTAL_SECTOR_ALIASES

AV, EMB, AI, FIN, OTHER = "autonomous_driving", "embodied_ai", "ai_infra", "finance", "other"
SECTORS = (AV, EMB, AI, FIN, OTHER)

# Sectors whose postings are never sent to a paid extractor (DeepSeek, GLM, Anthropic): titles,
# places, dates and levels come from free rules, and a seeker who wants a description read hands
# it to their own assistant (get_job). Howard 2026-11-17: new sectors cost us nothing (reports/150).
ZERO_EXTRACTION = (FIN,)

_BY_SECTOR: dict[str, tuple[str, ...]] = {
    FIN: (
        "cicc-hk", "citi-hk", "schonfeld-hk", "tower-research-hk", "airwallex-hk", "state-street-hk",
        "flow-traders-hk", "barclays-hk", "fidelity-intl-hk", "verition-hk", "worldquant-hk",
    ),
    AV: (
        "waymo", "kodiak", "motional", "torcrobotics", "botauto", "nuro", "weride", "zoox", "waabi",
        "aurorainnovation", "wayve", "robosense", "deeproute", "minieye", "freetech", "yushi", "rino",
        "trunk", "zvision", "motovis", "inceptio", "lixiang", "xiaopeng", "seyond", "blacksesame",
        "outsight", "aerovect", "saronic", "shieldai",
        'appliedintuition', 'plusai', 'stackav', 'maymobility', 'avride', 'aeva', 'skydio', 'anduril', 'wing', 'forterra', 'imagry', 'mobileye', 'gatik',
    ),
    EMB: (
        "figureai", "agilityrobotics", "skildai", "apptronik", "pathrobotics", "dexterity", "fieldai",
        "ambirobotics", "1x", "dynarobotics", "generalist", "standardbots", "cobot",
        "physicalintelligence", "carbonrobotics", "ekarobotics", "generalrobotics", "unitree", "galaxea",
        "ubtrobot", "dobot", "jaka", "mechmind", "megarobo", "pudutech", "hairobotics", "siasun",
        "yijiahe", "paxini", "magiclab", "galbot", "robotera", "fftai", "geekplus", "keenon", "astribot",
        "estun", "palrobotics", "flexion-robotics", "andromeda-robotics", "agile-robots", "robotec-ai",
        'bostondynamics', 'thebotcompany', 'humanoid', 'robco', 'viam', 'diligentrobotics', 'braincorp', 'serverobotics', 'cocorobotics', 'picklerobot', 'gecko-robotics', 'reflexrobotics', 'tutorintelligence', 'mujin', 'nimblerobotics', 'autostore', 'formic', 'machinalabs', 'bedrock-robotics', 'simberobotics', 'personaai', 'dreame', 'foundation-robotics', 'mytra', 'bonsai-robotics', 'wandelbots', 'franka-robotics', 'mentee-robotics',
    ),
    AI: (
        "anthropic", "openai", "mistral", "cohere", "databricks", "scaleai", "togetherai", "nebius",
        "coreweave", "crusoe", "cursor", "langchain", "etched", "replit", "perplexity", "baseten",
        "deepgram", "mercor", "suno", "writer", "reflectionai", "fireworksai", "modal", "normalcomputing",
        "tavus", "poolside", "lightning", "pika", "ideogram", "browserbase", "lancedb", "runway",
        "weaviate", "elevenlabs", "sierra", "decagon", "harvey", "abridge", "assemblyai", "stabilityai",
        "labelbox", "cresta", "gleanwork", "striveworks", "moonshot", "stepfun", "deepseek", "mthreads",
        "kunlunxin", "biren", "iluvatar", "iflytek", "4paradigm", "smartmore", "uipath", "nvidia",
    ),
    OTHER: (
        "datadog", "mongodb", "samsara", "verkada", "brex", "cloudflare", "elastic", "reddit", "affirm",
        "figma", "twilio", "gitlab", "instacart", "coinbase", "fivetran", "robinhood", "grafanalabs",
        "gusto", "faire", "chainguard", "sofi", "vercel", "abnormalsecurity", "newrelic", "mercury",
        "discord", "cribl", "fastly", "tailscale", "dropbox", "airtable", "mixpanel", "huntress",
        "cockroachlabs", "webflow", "honeycomb", "starburst", "planetscale", "imply", "netlify",
        "matchgroup", "temporaltechnologies", "clickhouse", "amplitude", "ramp", "linear", "palantir",
        "aift", "lynxanalytics", "atoms",
    ),
}

COMPANY_SECTOR: dict[str, str] = {cid: s for s, ids in _BY_SECTOR.items() for cid in ids}

SECTOR_NAMES_ZH = {AV: "自动驾驶", EMB: "具身智能 / 机器人", AI: "AI 基础设施与大模型", FIN: "金融（香港）", OTHER: "其他"}

# What a seeker types for each, in either language: the portal directory's words plus "other".
SECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    **{k: tuple(v) for k, v in _PORTAL_SECTOR_ALIASES.items()},
    FIN: ("finance", "financial services", "banking", "bank", "insurance", "asset management",
          "hedge fund", "trading", "金融", "银行", "銀行", "保险", "保險", "证券", "證券", "券商", "资管", "基金", "投行"),
    OTHER: ("other", "others", "其他", "其它"),
}


def sector_of(company_id: str | None) -> str | None:
    return COMPANY_SECTOR.get(company_id or "")


def resolve_sector(value: str | None) -> str | None:
    """The canonical sector for what the caller typed, or None when it names none."""
    v = " ".join(str(value or "").casefold().split())
    if not v:
        return None
    for sector, words in SECTOR_ALIASES.items():
        if v == sector or v in (w.casefold() for w in words):
            return sector
    return None


def zero_extraction(company_id: str | None) -> bool:
    """True when this employer's postings must never go to a paid extractor."""
    return sector_of(company_id) in ZERO_EXTRACTION


def company_ids_in(sector: str) -> list[str]:
    return list(_BY_SECTOR.get(sector, ()))
