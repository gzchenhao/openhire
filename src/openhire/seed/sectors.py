"""Which sector each indexed employer is in, so a seeker can say "autonomous-driving companies
only" (persona test, 2026-10-30: four of ten simulated seekers asked for exactly that and the
assistant had to search employer by employer; reports/107).

One label per employer, from what the company makes, the same four words everywhere:
  autonomous_driving  self-driving and driver assistance, the lidar / chips / trucks / cars
                      built for it, and autonomy off the road (drones, ships, airport tugs)
  embodied_ai         robots: humanoids, arms, mobile and warehouse robots, robot foundation models
  ai_infra            AI labs and models, AI chips and compute, AI developer tools and AI-first apps
  other               everything else the index carries (cloud software, fintech, consumer)

The first three match not_indexed.SECTORS, so list_portals and search_jobs mean the same thing
by a sector. A board the user added on their own machine has no label (sector_of returns None)
and is left out of a sector search rather than guessed. tests/test_sectors.py keeps every
seeded employer labelled: a new seed row without a sector here fails the suite.
"""

from __future__ import annotations

from .not_indexed import SECTOR_ALIASES as _PORTAL_SECTOR_ALIASES

AV, EMB, AI, OTHER = "autonomous_driving", "embodied_ai", "ai_infra", "other"
SECTORS = (AV, EMB, AI, OTHER)

_BY_SECTOR: dict[str, tuple[str, ...]] = {
    AV: (
        "waymo", "kodiak", "motional", "torcrobotics", "botauto", "nuro", "weride", "zoox", "waabi",
        "aurorainnovation", "wayve", "robosense", "deeproute", "minieye", "freetech", "yushi", "rino",
        "trunk", "zvision", "motovis", "inceptio", "lixiang", "xiaopeng", "seyond", "blacksesame",
        "outsight", "aerovect", "saronic", "shieldai",
        'appliedintuition', 'plusai', 'stackav', 'maymobility', 'avride', 'aeva', 'skydio', 'anduril', 'wing',
    ),
    EMB: (
        "figureai", "agilityrobotics", "skildai", "apptronik", "pathrobotics", "dexterity", "fieldai",
        "ambirobotics", "1x", "dynarobotics", "generalist", "standardbots", "cobot",
        "physicalintelligence", "carbonrobotics", "ekarobotics", "generalrobotics", "unitree", "galaxea",
        "ubtrobot", "dobot", "jaka", "mechmind", "megarobo", "pudutech", "hairobotics", "siasun",
        "yijiahe", "paxini", "magiclab", "galbot", "robotera", "fftai", "geekplus", "keenon", "astribot",
        "estun", "palrobotics", "flexion-robotics", "andromeda-robotics", "agile-robots", "robotec-ai",
        'bostondynamics', 'thebotcompany', 'humanoid', 'robco', 'viam', 'diligentrobotics', 'braincorp', 'serverobotics', 'cocorobotics', 'picklerobot', 'gecko-robotics', 'reflexrobotics', 'tutorintelligence', 'mujin', 'nimblerobotics', 'autostore', 'formic', 'machinalabs', 'bedrock-robotics', 'simberobotics', 'personaai', 'dreame',
    ),
    AI: (
        "anthropic", "openai", "mistral", "cohere", "databricks", "scaleai", "togetherai", "nebius",
        "coreweave", "crusoe", "cursor", "langchain", "etched", "replit", "perplexity", "baseten",
        "deepgram", "mercor", "suno", "writer", "reflectionai", "fireworksai", "modal", "normalcomputing",
        "tavus", "poolside", "lightning", "pika", "ideogram", "browserbase", "lancedb", "runway",
        "weaviate", "elevenlabs", "sierra", "decagon", "harvey", "abridge", "assemblyai", "stabilityai",
        "labelbox", "cresta", "gleanwork", "striveworks", "moonshot", "stepfun", "deepseek", "mthreads",
        "kunlunxin", "biren", "iluvatar", "iflytek", "4paradigm", "smartmore", "uipath",
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

SECTOR_NAMES_ZH = {AV: "自动驾驶", EMB: "具身智能 / 机器人", AI: "AI 基础设施与大模型", OTHER: "其他"}

# What a seeker types for each, in either language: the portal directory's words plus "other".
SECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    **{k: tuple(v) for k, v in _PORTAL_SECTOR_ALIASES.items()},
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


def company_ids_in(sector: str) -> list[str]:
    return list(_BY_SECTOR.get(sector, ()))
