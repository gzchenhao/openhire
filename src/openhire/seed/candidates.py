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


# --- Greenhouse ---------------------------------------------------------------
_GREENHOUSE = [
    ("anthropic", "Anthropic"),
    ("databricks", "Databricks"),
    ("datadog", "Datadog"),
    ("mongodb", "MongoDB"),
    ("waymo", "Waymo"),
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
    ("temporaltechnologies", "Temporal"),
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
]

# --- Ashby --------------------------------------------------------------------
_ASHBY = [
    ("openai", "OpenAI"),
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
    ("fireworksai", "Fireworks AI"),
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


def all_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for vendor, rows in (("greenhouse", _GREENHOUSE), ("lever", _LEVER), ("ashby", _ASHBY)):
        for tenant, name in rows:
            out.append(Candidate(vendor=vendor, tenant=tenant, name=name))
    return out


def candidate_count() -> int:
    return len(_GREENHOUSE) + len(_LEVER) + len(_ASHBY)
