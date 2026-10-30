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

from ..ats.self_reported import SELF_REPORTED_EMPLOYERS


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
    ("kodiak", "Kodiak Robotics"),
    ("motional", "Motional"),
    ("torcrobotics", "Torc Robotics"),
    ("botauto", "Bot Auto"),
    ("figureai", "Figure"),
    ("agilityrobotics", "Agility Robotics"),
    # 2026-10-08 embodied-AI startups found by the SME careers-page survey (reports/060);
    # each board answered the public API with its postings on that day.
    ("skildai-careers", "Skild AI", "skildai"),
    ("apptronik", "Apptronik"),
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
    # 2026-10-21, the maintainer: Hong Kong employers in, plus every Hong Kong employer in our
    # sectors with a readable board (reports/086). Each read live that day, dates on every row.
    ("aift", "AIFT"),                       # Hong Kong insurtech AI: 27 postings, 10 in Hong Kong
    ("lynxanalytics", "Lynx Analytics"),    # AI / graph analytics: 7 postings
    ("cssmerge", "Atoms", "atoms"),         # the board is named "ATOMS Careers page": robotics (Lab37), autonomous haulage (Pronto) and food-tech brands; 333 postings, Sheung Wan office
    # 2026-10-30, the AV / embodied survey (reports/119): found on the employers' own careers
    # pages and read live with this adapter the same day.
    ('stackav', 'Stack AV'),  # 13 live
    ('maymobility', 'May Mobility'),  # 38 live
    ('avride', 'Avride'),  # 46 live
    ('andurilindustries', 'Anduril', 'anduril'),  # 2555 live
    ('wing', 'Wing'),  # 56 live
    ('viamrobotics', 'Viam', 'viam'),  # 8 live
    ('diligentrobotics', 'Diligent Robotics'),  # 10 live
    ('braincorporation', 'Brain Corp', 'braincorp'),  # 10 live
    ('nimblerobotics', 'Nimble Robotics'),  # 40 live
    ('formic', 'Formic'),  # 41 live
]

# --- Lever --------------------------------------------------------------------
_LEVER = [
    ("shieldai", "Shield AI"),
    ("palantir", "Palantir"),
    ("mistral", "Mistral AI"),
    ("matchgroup", "Match Group"),
    ("weride", "文远知行 WeRide"),
    # v0.2 autonomous-driving / embodied-AI expansion (each verified live).
    ("zoox", "Zoox"),
    ("waabi", "Waabi"),
    ("dexterity", "Dexterity"),
    ("field-ai", "Field AI", "fieldai"),  # 2026-10-08, see reports/060
    ("ambirobotics", "Ambi Robotics"),
    ("outsight", "Outsight"),  # 2026-10-21 (reports/086): lidar perception software, France; 11 postings
    # 2026-10-30, the AV / embodied survey (reports/119): found on the employers' own careers
    # pages and read live with this adapter the same day.
    ('plus-2', 'PlusAI', 'plusai'),  # 45 live
    ('aeva', 'Aeva'),  # 45 live
    ('picklerobot', 'Pickle Robot'),  # 9 live
    ('tutorintelligence', 'Tutor Intelligence'),  # 59 live
    ('mujininc', 'Mujin', 'mujin'),  # 88 live
    ('MachinaLabs', 'Machina Labs', 'machinalabs'),  # 28 live
    ('SimbeRobotics', 'Simbe Robotics', 'simberobotics'),  # 17 live
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
    # Greenhouse -> Ashby, 2026-10 (the Greenhouse boards 404 since September; found by the
    # local session on each careers page and read live 2026-10-28: ClickHouse 207, Wayve 180,
    # Amplitude 43, Carbon Robotics 3). Same company ids, so their history stays attached and
    # the stale Greenhouse rows are delisted on the first Ashby crawl (reports/102).
    ("clickhouse", "ClickHouse"),
    ("wayve", "Wayve"),
    ("amplitude", "Amplitude"),
    ("carbon-robotics", "Carbon Robotics", "carbonrobotics"),
    # v0.2 autonomous-driving / embodied-AI expansion (each verified live).
    ("1x", "1X Technologies"),
    # 2026-10-08 embodied-AI startups (reports/060), each verified live on the public board API.
    ("dyna-robotics", "Dyna Robotics", "dynarobotics"),
    ("generalist", "Generalist AI"),
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
    # 2026-10-21 (reports/086), each read live that day.
    ("uipath", "UiPath"),                    # agentic automation: 107 postings, 3 in Hong Kong
    ("ekarobotics", "Eka"),                  # robotics, Boston: 11 postings
    ("generalrobotics", "General Robotics"), # robot intelligence platform, Redmond + Singapore: 14 postings
    # 2026-10-30, the AV / embodied survey (reports/119): found on the employers' own careers
    # pages and read live with this adapter the same day.
    ('applied', 'Applied Intuition', 'appliedintuition'),  # 327 live
    ('skydio', 'Skydio'),  # 185 live
    ('thebotcompany', 'The Bot Company'),  # 7 live
    ('humanoid', 'Humanoid'),  # 96 live
    ('robco', 'RobCo'),  # 32 live
    ('serverobotics', 'Serve Robotics'),  # 27 live
    ('cocodelivery', 'Coco Robotics', 'cocorobotics'),  # 7 live
    ('gecko-robotics', 'Gecko Robotics'),  # 21 live
    ('ReflexRobotics', 'Reflex Robotics', 'reflexrobotics'),  # 8 live
    ('bedrock-robotics', 'Bedrock Robotics'),  # 58 live
    ('persona.ai', 'Persona AI', 'personaai'),  # 27 live
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
    # Added 2026-09-06: tactile-sensor + dexterous-hand maker, core embodied-AI supply
    # chain (probe hit: 122 social postings on paxini.zhiye.com).
    ("paxini", "帕西尼 PaXini"),
    # 2026-10-20: found from the employers' own careers pages by the maintainer's local
    # session (reports/084) and read live with this adapter the same day.
    ("magiclab", "魔法原子 MagicLab"),        # 73 live, humanoid robots
    ("mthreads", "摩尔线程 Moore Threads"),   # 206 live, GPU / AI compute (AI infra)
    # 2026-10-21, the Hong Kong survey (reports/086): read live that day, dates on every row.
    ("iflytek", "科大讯飞 iFLYTEK"),                  # 719 live, Spark LLM / speech AI; 4 in Hong Kong (Cyberport international HQ)
    ("bsthr", "黑芝麻智能 Black Sesame", "blacksesame"),  # 100 live, ADAS / autonomous-driving chips, HK-listed
    ("kunlunxin1", "昆仑芯 Kunlunxin", "kunlunxin"),      # 32 live, AI chips
    ("estun1", "埃斯顿 Estun", "estun"),                  # 43 live, industrial robots
    # 2026-10-30, the AV / embodied survey (reports/119): found on the employers' own careers
    # pages and read live with this adapter the same day.
    ('dreame', '追觅 Dreame'),  # 2000 live
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
    # 2026-09-23: three Moka portals found while mapping Feishu-hosted employers (reports/053).
    # All three verified with this adapter: plain init-data, posted_at present, JD present.
    ("yinhetongyong/165929", "银河通用 Galbot", "galbot"),          # 118 live, 具身 (social hiring; campus is on Feishu)
    ("moonshot/148506", "月之暗面 Moonshot AI", "moonshot"),        # 105 live, AI lab
    ("step/94904", "阶跃星辰 StepFun", "stepfun"),                   # 217 live, AI lab
    ("freetech/42354", "福瑞泰克 Freetech", "freetech"),
    ("yushi/3774", "驭势科技 UISEE", "yushi"),
    ("rino/165980", "白犀牛 Rino.ai", "rino"),
    ("trunk/39504", "主线科技 Trunk Tech", "trunk"),
    ("robotera/163877", "星动纪元 Robot Era", "robotera"),
    ("fftai/126181", "傅利叶 Fourier", "fftai"),
    ("zvision/43353", "一径科技 ZVISION", "zvision"),
    ("geekplus/5030", "极智嘉 Geek+", "geekplus"),
    ("keenon/24672", "擎朗智能 Keenon", "keenon"),
    # 2026-09-03 leader ruling (reports/020 §拍板): admission criterion is now "first-tier
    # in-house AD/embodied-AI investment", not the primary-business label — XPeng qualifies
    # (XNGP + humanoid Iron); Dreame (appliances) and Inovance (components) still do not.
    ("xiaopeng/67918", "小鹏汇天 XPeng AeroHT", "xiaopeng"),
    # 2026-10-20: found from the employers' own careers pages (reports/084); each read live
    # with this adapter the same day, posting dates present. The portals link as
    # /social-recruitment/<org>/<siteId>; the same pair answers on /apply/.
    ("astribot/144861", "星尘智能 Astribot", "astribot"),          # 43 live, humanoid robots
    ("motovis/38410", "魔视智能 Motovis", "motovis"),               # 9 live, ADAS / autonomous driving
    ("inceptio-ai/150619", "嬴彻科技 Inceptio", "inceptio"),         # 97 live, autonomous trucking
    # DeepSeek's own careers page (talent.deepseek.com) links every role to this tenant,
    # which is named after its parent 幻方 (High-Flyer); the roles are DeepSeek's.
    ("high-flyer/140576", "深度求索 DeepSeek", "deepseek"),          # 36 live, AI lab
    # 2026-10-21, the Hong Kong survey (reports/086): read live that day, dates on every row.
    ("biren/44726", "壁仞科技 Biren", "biren"),                # 51 live, GPU; Hong Kong regional HQ at Cyberport
    ("iluvatar/98705", "天数智芯 Iluvatar CoreX", "iluvatar"),  # 62 live, GPU
    ("smartmore/40505", "思谋科技 SmartMore", "smartmore"),     # 24 live, industrial vision AI
    ("4paradigm/5072", "第四范式 4Paradigm", "4paradigm"),      # 2 live, AI platform, HK-listed
]

# --- NIO 蔚来 (`www.nio.cn/careers/jobs`): a first-party employer mirror, not an ATS ---
# Added 2026-09-23. NIO hires through Feishu Hire, whose API signs requests and is
# therefore off limits (reports/014); the employer's own careers page carries the same
# 1,784-row 社招 roster in the clear inside `__NEXT_DATA__`, so that is what is read.
# robots.txt leaves /careers open and the page answers a plain curl GET with no cookie
# and no token. The mirror carries no JD and no salary, so those stay empty; see ats/nio.py.
#
# PARKED 2026-09-23: the site's edge (Tencent EdgeOne) blocks this crawler's HTTP client
# with a 567 "请求已被站点的安全策略拦截" page while letting curl through, i.e. it sorts
# clients by TLS handshake. That is the owner's bot-management policy, which reports/020
# files under access control, so it is not worked around and the row is not in the active
# roster: a weekly `ohp seed` knocking on a door that said no is not politeness. Uncomment
# once NIO has been asked (the block page carries a request ID for exactly that) or the
# policy changes; the adapter, tests and trust list are all in place.
_NIO: list[tuple[str, str]] = [
    # ("nio", "蔚来 NIO"),
]


# --- First-party employer mirrors (no ATS vendor) --------------------------------------
# Some employers publish their roster through their own public API rather than an ATS.
# Each such employer is its own vendor with exactly one tenant, and the tenant names the
# board in the API path. Admission criterion is the same as everywhere else in this file:
# first-tier in-house AD / embodied-AI investment, verified live with plain GETs and no
# signature, cookie or login (reports/020 boundary).
#
# Li Auto 理想汽车, verified 2026-09-23: 772 社招 postings on `api-web.lixiang.com`. The
# mirror carries NO posting date on any row, so every Li Auto posting ages from the day
# we first saw it (`date_signal: "not_reported_by_ats"`), never from an invented date.
# The `school` (校招) board is deliberately excluded, as Beisen's 校招 category is.
_LIXIANG = [
    ("social", "理想汽车 Li Auto", "lixiang"),
]

# --- Workable ----------------------------------------------------------------------
# Each board read live on 2026-10-12 through the local task queue (reports/075 §5, 076):
# the cloud session cannot reach apply.workable.com, so the maintainer's machine did.
_WORKABLE = [
    ("robotec-ai", "Robotec.ai"),  # robotics simulation / physical-AI tooling, Warsaw: 6 postings, dated
    ("flexion-robotics", "Flexion Robotics"),  # humanoid intelligence layer, Zürich + SF: 14 job-city rows
    ("andromeda-robotics", "Andromeda Robotics"),  # companion humanoid, SF + Melbourne: 16 rows
    ("agile-robots", "Agile Robots"),  # industrial + humanoid robotics; the board carries the US roles: 4 rows
]

# --- SmartRecruiters ----------------------------------------------------------------
# Same day, same route. The tenant keeps the vendor's casing (it is part of the URL); the
# company slug is ours and lowercase like every other.
_SMARTRECRUITERS = [
    ("AeroVect", "AeroVect", "aerovect"),  # autonomous airport tow tractors, SF: 6 postings, all dated 2020-2022
    ("PalRobotics", "PAL Robotics", "palrobotics"),  # humanoid service robots, Barcelona: 3 postings
]

# --- Employer self-reported rosters (ats/self_reported.py) ---------------------------------
# The door for employers whose own system we cannot read (reports/060). Derived from the
# adapter's registry so an employer is declared in exactly one place, after the maintainer
# verified the corporate identity behind the roster. The tenant is our own slug.
# --- Workday (`<account>.wdN.myworkdayjobs.com/<site>`) ------------------------
# 2026-10-30 (reports/119): the first Workday tenants in the seed, read live that day from
# an unrestricted network (the cloud default network cannot reach myworkdayjobs.com).
_WORKDAY = [
    ('bostondynamics.wd1/Boston_Dynamics', 'Boston Dynamics', 'bostondynamics'),  # 87 live
    ('autostore.wd3/autostore', 'AutoStore', 'autostore'),  # 33 live
]

# --- Rippling (`ats.rippling.com/<slug>/jobs`) and Personio (`<slug>.jobs.personio.de`) ---
# 2026-10-30 (reports/121): readers ported from career-ops (MIT); every tenant read live that
# day with our default client. Rippling's list carries no posting date (date_signal
# not_reported_by_ats); Personio's XML feed carries createdAt.
_RIPPLING = [
    ('forterra', 'Forterra', 'forterra'),  # 55 live
    ('foundation-robotics', 'Foundation Robotics', 'foundation-robotics'),  # 26 live
    ('mytra', 'Mytra', 'mytra'),  # 43 live
    ('bonsairoboticsmain', 'Bonsai Robotics', 'bonsai-robotics'),  # 8 live
]
_PERSONIO = [
    ('wandelbots', 'Wandelbots', 'wandelbots'),  # 11 live
    ('franka-robotics', 'Franka Robotics', 'franka-robotics'),  # 3 live
]

# --- Comeet (key "<slug>/<uid>/<token>") ------------------------------------------
# 2026-10-30 (reports/122): reader ported from career-ops (MIT). The uid and careers token
# are the ones the employer's own careers page publishes in plain text for this read
# (Imagry: imagry.co/careers, inline `comeetvar`). 7 live that day.
_COMEET = [
    ('imagry/B7.00F/7BF2E7A1EFC1EFCF7E7BF36393DF826BB2E7A', 'Imagry', 'imagry'),
]

_SELF_REPORTED = [(e.slug, e.name) for e in SELF_REPORTED_EMPLOYERS.values()]


def all_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for vendor, rows in (
        ("greenhouse", _GREENHOUSE),
        ("lever", _LEVER),
        ("ashby", _ASHBY),
        ("beisen", _BEISEN),
        ("moka", _MOKA),
        ("lixiang", _LIXIANG),
        ("nio", _NIO),
        ("workable", _WORKABLE),
        ("smartrecruiters", _SMARTRECRUITERS),
        ("workday", _WORKDAY),
        ("rippling", _RIPPLING),
        ("personio", _PERSONIO),
        ("comeet", _COMEET),
        ("self_reported", _SELF_REPORTED),
    ):
        for row in rows:
            tenant, name = row[0], row[1]
            company_id = row[2] if len(row) > 2 else None
            out.append(
                Candidate(vendor=vendor, tenant=tenant, name=name, company_id=company_id)
            )
    return out


def candidate_count() -> int:
    return (
        len(_GREENHOUSE) + len(_LEVER) + len(_ASHBY) + len(_BEISEN) + len(_MOKA)
        + len(_LIXIANG)
        + len(_NIO)
        + len(_WORKABLE)
        + len(_SMARTRECRUITERS)
        + len(_WORKDAY)
        + len(_RIPPLING)
        + len(_PERSONIO)
        + len(_COMEET)
        + len(_SELF_REPORTED)
    )
