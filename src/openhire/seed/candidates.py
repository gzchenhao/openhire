"""Seed roster — remote-friendly AI / Infra employers on public ATSes.

Every (vendor, tenant) below was **verified live** (HTTP 200 + well-formed jobs array)
during seed-list construction, but is re-verified at runtime by `ohp seed`: a tenant
only enters `companies` when its public API currently returns jobs. Slugs drift as
companies migrate ATS, so `ohp seed` is the source of truth, not this file.

Discovery method (per handoff §数据源): ATS board-URL fingerprints
(boards.greenhouse.io/x · jobs.lever.co/x · jobs.ashbyhq.com/x) + reverse lookup from
the careers pages of well-known AI/Infra companies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    vendor: str
    tenant: str
    name: str
    # Our own stable slug for the employer, used as `companies.id` and therefore as the
    # prefix of every job PK. Normally identical to the ATS tenant — but when a company
    # migrates ATS (or its board slug drifts) the tenant changes while this must NOT, or
    # the whole job history would be orphaned under a dead company row. Defaults to the
    # tenant so the ordinary case stays a two-tuple.
    company_id: str | None = None

    @property
    def slug(self) -> str:
        return self.company_id or self.tenant


# --- Greenhouse ---------------------------------------------------------------
_GREENHOUSE = [
    ("anthropic", "Anthropic"),
    ("databricks", "Databricks"),
    ("datadog", "Datadog"),
    ("mongodb", "MongoDB"),
    ("waymo", "Waymo"),
    # v0.2 autonomous-driving / embodied-AI expansion (each verified live).
    # NOTE: Aurora moved to Ashby (see _ASHBY) — its Greenhouse board is gone.
    ("wayve", "Wayve"),
    ("kodiak", "Kodiak Robotics"),
    ("motional", "Motional"),
    ("torcrobotics", "Torc Robotics"),
    ("botauto", "Bot Auto"),
    ("figureai", "Figure"),
    ("agilityrobotics", "Agility Robotics"),
    ("carbonrobotics", "Carbon Robotics"),
    ("pathrobotics", "Path Robotics"),
    ("nebius", "Nebius"),
    ("samsara", "Samsara"),
    ("verkada", "Verkada"),
    ("coreweave", "CoreWeave"),
    ("brex", "Brex"),
    ("cloudflare", "Cloudflare"),
    ("elastic", "Elastic"),
    ("scaleai", "Scale AI"),
    ("reddit", "Reddit"),
    ("affirm", "Affirm"),
    ("figma", "Figma"),
    ("clickhouse", "ClickHouse"),
    ("twilio", "Twilio"),
    ("gitlab", "GitLab"),
    ("instacart", "Instacart"),
    ("coinbase", "Coinbase"),
    ("gleanwork", "Glean"),
    ("fivetran", "Fivetran"),
    ("robinhood", "Robinhood"),
    ("grafanalabs", "Grafana Labs"),
    ("cresta", "Cresta"),
    ("nuro", "Nuro"),
    ("gusto", "Gusto"),
    ("faire", "Faire"),
    ("chainguard", "Chainguard"),
    ("sofi", "SoFi"),
    ("vercel", "Vercel"),
    ("togetherai", "Together AI"),
    ("abnormalsecurity", "Abnormal Security"),
    ("newrelic", "New Relic"),
    ("mercury", "Mercury"),
    ("discord", "Discord"),
    ("cribl", "Cribl"),
    ("fastly", "Fastly"),
    ("amplitude", "Amplitude"),
    ("tailscale", "Tailscale"),
    ("dropbox", "Dropbox"),
    ("airtable", "Airtable"),
    ("mixpanel", "Mixpanel"),
    ("huntress", "Huntress"),
    ("cockroachlabs", "Cockroach Labs"),
    ("webflow", "Webflow"),
    ("striveworks", "Striveworks"),
    ("honeycomb", "Honeycomb"),
    ("labelbox", "Labelbox"),
    ("starburst", "Starburst"),
    ("planetscale", "PlanetScale"),
    ("imply", "Imply"),
    ("assemblyai", "AssemblyAI"),
    ("netlify", "Netlify"),
    ("stabilityai", "Stability AI"),
]

# --- Lever --------------------------------------------------------------------
_LEVER = [
    ("shieldai", "Shield AI"),
    ("palantir", "Palantir"),
    ("mistral", "Mistral AI"),
    ("matchgroup", "Match Group"),
    ("weride", "WeRide"),
    # v0.2 autonomous-driving / embodied-AI expansion (each verified live).
    ("zoox", "Zoox"),
    ("waabi", "Waabi"),
    ("dexterity", "Dexterity"),
    ("ambirobotics", "Ambi Robotics"),
]

# --- Ashby --------------------------------------------------------------------
# (tenant, name) or (tenant, name, company_id) — the third element pins our slug when
# the ATS tenant has drifted away from it (2026-08-31 migrations, each verified live).
_ASHBY = [
    ("openai", "OpenAI"),
    # Greenhouse -> Ashby. Board name found via aurora.tech's own `ashbyOrgSlug`.
    ("aurora-operations-inc", "Aurora", "aurorainnovation"),
    # Greenhouse -> Ashby. Confirmed: job UUIDs on temporal.io/careers are in this board.
    ("temporal", "Temporal", "temporaltechnologies"),
    # v0.2 autonomous-driving / embodied-AI expansion (each verified live).
    ("1x", "1X Technologies"),
    ("standardbots", "Standard Bots"),
    ("saronic", "Saronic"),
    ("cobot", "Collaborative Robotics"),
    ("crusoe", "Crusoe"),
    ("harvey", "Harvey"),
    ("elevenlabs", "ElevenLabs"),
    ("sierra", "Sierra"),
    ("cohere", "Cohere"),
    ("ramp", "Ramp"),
    ("decagon", "Decagon"),
    ("cursor", "Cursor"),
    ("langchain", "LangChain"),
    ("etched", "Etched"),
    ("replit", "Replit"),
    ("perplexity", "Perplexity"),
    ("baseten", "Baseten"),
    ("deepgram", "Deepgram"),
    ("mercor", "Mercor"),
    ("suno", "Suno"),
    ("writer", "Writer"),
    ("reflectionai", "Reflection AI"),
    ("abridge", "Abridge"),
    # Ashby board slug shortened: fireworksai -> fireworks (same ATS, same company).
    ("fireworks", "Fireworks AI", "fireworksai"),
    ("modal", "Modal Labs"),
    ("linear", "Linear"),
    ("physicalintelligence", "Physical Intelligence"),
    ("normalcomputing", "Normal Computing"),
    ("tavus", "Tavus"),
    ("poolside", "Poolside"),
    ("lightning", "Lightning AI"),
    ("pika", "Pika"),
    ("ideogram", "Ideogram"),
    ("browserbase", "Browserbase"),
    ("lancedb", "LanceDB"),
    ("runway", "Runway"),
    ("weaviate", "Weaviate"),
]

# --- Beisen 北森 (`<tenant>.zhiye.com`) — domestic CN autonomous-driving / embodied AI ---
# Added in v0.2 to cover the target industry inside China. Feishu Hire (飞书招聘) covers more
# CN employers but signs its job-list requests with a ByteDance `_signature`, so it is not
# publicly crawlable and is deliberately absent — see reports/014.
_BEISEN = [
    ("unitree", "宇树科技 Unitree"),
    ("galaxea", "星海图 Galaxea"),
    ("ubtrobot", "优必选 UBTECH"),
    ("dobot", "越疆 Dobot"),
    ("jaka", "节卡机器人 JAKA"),
    ("mechmind", "梅卡曼德 Mech-Mind"),
    ("megarobo", "镁伽 MegaRobo"),
    ("pudutech", "普渡科技 Pudu Robotics"),
    ("hairobotics", "海柔创新 Hai Robotics"),
    ("siasun", "新松机器人 SIASUN"),
    ("seyond", "图达通 Seyond"),
    # Re-checked in 020: the 014 "non-JSON" reading no longer reproduces — the tenant
    # answers the standard endpoint with 134 postings. Its sibling `zhito` (挚途科技) is
    # still absent on purpose: that portal runs Beisen's legacy CmsPortal build, which has
    # no JSON endpoint at all, and it currently lists 无任何在招职位.
    ("yijiahe", "亿嘉和 YIJIAHE"),
]


# --- Moka 摩卡 (`app.mokahr.com/apply/<org>/<siteId>`) — the second domestic vendor ---
# Added in 020. `tenant` is the org/siteId pair because that pair *is* the portal address;
# `company_id` stays the bare org slug so a site-id change never orphans job history.
# Every entry below was verified live on 2026-09-02 (portal page carries an `org` record
# and the public roster endpoint returns jobs) — a bogus slug also answers HTTP 200, so
# the org record, not the status code, is the existence test. See reports/020.
_MOKA = [
    ("robosense/77883", "速腾聚创 RoboSense", "robosense"),
    ("deeproute/143885", "元戎启行 DeepRoute", "deeproute"),
    ("minieye/118570", "佑驾创新 MINIEYE", "minieye"),
    ("freetech/42354", "福瑞泰克 Freetech", "freetech"),
    ("yushi/3774", "驭势科技 UISEE", "yushi"),
    ("rino/165980", "白犀牛 Rino.ai", "rino"),
    ("trunk/39504", "主线科技 Trunk Tech", "trunk"),
    ("robotera/163877", "星动纪元 Robot Era", "robotera"),
    ("fftai/126181", "傅利叶 Fourier", "fftai"),
    ("zvision/43353", "一径科技 ZVISION", "zvision"),
    ("geekplus/5030", "极智嘉 Geek+", "geekplus"),
    ("keenon/24672", "擎朗智能 Keenon", "keenon"),
]


def all_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for vendor, rows in (
        ("greenhouse", _GREENHOUSE),
        ("lever", _LEVER),
        ("ashby", _ASHBY),
        ("beisen", _BEISEN),
        ("moka", _MOKA),
    ):
        for row in rows:
            tenant, name = row[0], row[1]
            company_id = row[2] if len(row) > 2 else None
            out.append(
                Candidate(vendor=vendor, tenant=tenant, name=name, company_id=company_id)
            )
    return out


def candidate_count() -> int:
    return len(_GREENHOUSE) + len(_LEVER) + len(_ASHBY) + len(_BEISEN) + len(_MOKA)
