"""Pluggable JD extraction — skills[], remote_policy, salary.

Contract (README §LLM 抽取): extraction runs **only when content_hash changes**. It
pulls skills (lowercase-normalized), remote_policy, and salary *if the JD states one*.
v0.1 does NOT infer salary — absent salary stays NULL, `salary_inferred` is left False
(that flag is reserved for v0.2).

The extractor is an interface with two implementations:
  * AnthropicExtractor — default when an API key is present (OPENHIRE_ANTHROPIC_API_KEY).
  * HeuristicExtractor — dependency-free fallback so the pipeline runs fully offline
    and in CI. Deterministic; good enough to populate a searchable index.

Swap in any other backend by implementing `Extractor.extract`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from .. import config
from ..ats.base import JobRecord

REMOTE_POLICIES = ("remote", "hybrid", "onsite", "unknown")


@dataclass
class ExtractionResult:
    skills: list[str] = field(default_factory=list)
    remote_policy: str = "unknown"
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None


class Extractor(Protocol):
    name: str

    def extract(self, job: JobRecord) -> ExtractionResult: ...


# --- Shared skill vocabulary --------------------------------------------------
# canonical lowercase tag -> alias regexes (word-boundary matched, case-insensitive).
_SKILL_VOCAB: dict[str, list[str]] = {
    "python": [r"python"],
    "rust": [r"rust"],
    "go": [r"golang", r"\bgo\b"],
    "typescript": [r"typescript", r"\bts\b"],
    "javascript": [r"javascript"],
    "java": [r"\bjava\b"],
    "c++": [r"c\+\+", r"cplusplus"],
    "scala": [r"scala"],
    "ruby": [r"\bruby\b"],
    "elixir": [r"elixir"],
    "kotlin": [r"kotlin"],
    "swift": [r"\bswift\b"],
    "sql": [r"\bsql\b"],
    "k8s": [r"kubernetes", r"k8s"],
    "docker": [r"docker"],
    "terraform": [r"terraform"],
    "aws": [r"\baws\b", r"amazon web services"],
    "gcp": [r"\bgcp\b", r"google cloud"],
    "azure": [r"azure"],
    "kafka": [r"kafka"],
    "spark": [r"\bspark\b"],
    "airflow": [r"airflow"],
    "postgres": [r"postgres", r"postgresql"],
    "redis": [r"redis"],
    "grpc": [r"grpc"],
    "graphql": [r"graphql"],
    "react": [r"react"],
    "node": [r"node\.?js"],
    "llm": [r"\bllm\b", r"large language model"],
    "rag": [r"\brag\b", r"retrieval[- ]augmented"],
    "nlp": [r"\bnlp\b", r"natural language processing"],
    "pytorch": [r"pytorch"],
    "tensorflow": [r"tensorflow"],
    "jax": [r"\bjax\b"],
    "cuda": [r"cuda"],
    "triton": [r"triton"],
    "transformers": [r"transformer"],
    "ml": [r"machine learning", r"\bml\b"],
    "mlops": [r"mlops"],
    "distributed-systems": [r"distributed systems?"],
    "gpu": [r"\bgpu\b", r"gpus"],
    "inference": [r"inference"],
    "vector-db": [r"vector (database|db|store)", r"embeddings?"],
    "data-eng": [r"data engineer", r"data pipeline"],
    "security": [r"security engineer", r"appsec", r"infosec"],
    "networking": [r"networking", r"\btcp/ip\b"],
    "compilers": [r"compilers?"],
    "cuda-kernels": [r"kernel (development|programming)"],
}
_COMPILED_VOCAB = {
    tag: [re.compile(p, re.I) for p in pats] for tag, pats in _SKILL_VOCAB.items()
}

# e.g. "$180,000 - $240,000", "$180k–$240k", "USD 180000 to 240000"
_SALARY_RE = re.compile(
    r"(?P<cur>\$|usd|eur|€|gbp|£)?\s*"
    r"(?P<lo>\d{2,3}(?:[,\.]\d{3})?)\s*(?P<lok>k)?"
    r"\s*(?:-|–|—|to)\s*"
    r"(?P<cur2>\$|usd|eur|€|gbp|£)?\s*"
    r"(?P<hi>\d{2,3}(?:[,\.]\d{3})?)\s*(?P<hik>k)?",
    re.I,
)
_CUR_MAP = {"$": "USD", "usd": "USD", "eur": "EUR", "€": "EUR", "gbp": "GBP", "£": "GBP"}


# Canonical aliases so any extractor emits the SAME tag (search matching is exact).
# The heuristic already emits canonical tags; LLMs return free-form, so we map them.
_SKILL_ALIASES = {
    "kubernetes": "k8s", "k8s": "k8s",
    "cpp": "c++", "c/c++": "c++",
    "golang": "go",
    "ts": "typescript",
    "postgresql": "postgres", "postgre": "postgres",
    "node.js": "node", "nodejs": "node",
    "retrieval-augmented generation": "rag", "retrieval augmented generation": "rag",
    "large language model": "llm", "large language models": "llm", "llms": "llm",
    "natural language processing": "nlp",
    "machine learning": "ml",
    "google cloud": "gcp", "google cloud platform": "gcp",
    "amazon web services": "aws",
    "distributed systems": "distributed-systems", "distributed system": "distributed-systems",
    "vector database": "vector-db", "vector databases": "vector-db",
    "vector db": "vector-db", "embeddings": "vector-db", "embedding": "vector-db",
    "gpus": "gpu",
    "tensorflow": "tensorflow", "tf": "tensorflow",
}


def canonicalize_skill(tag: str) -> str:
    t = tag.strip().lower()
    return _SKILL_ALIASES.get(t, t)


def canonicalize_skills(tags: list[str]) -> list[str]:
    """Normalize skill tags to canonical forms, de-duplicated, order preserved."""
    out: list[str] = []
    for t in tags:
        c = canonicalize_skill(t)
        if c and c not in out:
            out.append(c)
    return out


def extract_skills(text: str, limit: int = 12) -> list[str]:
    found: list[str] = []
    for tag, patterns in _COMPILED_VOCAB.items():
        if any(p.search(text) for p in patterns):
            found.append(tag)
    return found[:limit]


def _parse_salary_number(num: str, has_k: bool) -> int | None:
    try:
        val = float(num.replace(",", ""))
    except ValueError:
        return None
    if has_k:
        val *= 1000
    return int(val)


def extract_salary_from_text(text: str) -> tuple[int | None, int | None, str | None]:
    """Only returns a range when the JD explicitly states one; no inference."""
    for m in _SALARY_RE.finditer(text):
        lo = _parse_salary_number(m.group("lo"), bool(m.group("lok")))
        hi = _parse_salary_number(m.group("hi"), bool(m.group("hik")))
        if lo is None or hi is None:
            continue
        # Guard against nonsense (dates, versions). Require plausible comp band.
        if hi < lo or hi < 20_000 or hi > 5_000_000:
            continue
        cur_raw = (m.group("cur") or m.group("cur2") or "").lower()
        return lo, hi, _CUR_MAP.get(cur_raw)
    return None, None, None


def _resolve_remote(job: JobRecord, text: str) -> str:
    if job.remote_hint in ("remote", "hybrid", "onsite"):
        return job.remote_hint
    if re.search(r"\bfully remote\b|\b100% remote\b|\bremote[- ]first\b", text):
        return "remote"
    if re.search(r"\bhybrid\b", text):
        return "hybrid"
    if re.search(r"\bon[- ]?site\b|\bin[- ]?office\b", text):
        return "onsite"
    if job.location and "remote" in job.location.lower():
        return "remote"
    return "unknown"


class HeuristicExtractor:
    name = "heuristic"

    def extract(self, job: JobRecord) -> ExtractionResult:
        text = f"{job.title}\n{job.description_raw}"
        skills = extract_skills(text)
        remote = _resolve_remote(job, text)
        # Prefer structured ATS compensation; fall back to JD text (still not inference).
        smin, smax, scur = job.salary_min, job.salary_max, job.salary_currency
        if smin is None and smax is None:
            smin, smax, scur = extract_salary_from_text(job.description_raw or "")
        return ExtractionResult(
            skills=skills,
            remote_policy=remote,
            salary_min=smin,
            salary_max=smax,
            salary_currency=scur,
        )


_ANTHROPIC_TOOL = {
    "name": "record_job_facts",
    "description": "Record structured facts extracted from a job description.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lowercase technical skill tags, e.g. rust, k8s, rag, cuda.",
            },
            "remote_policy": {"type": "string", "enum": list(REMOTE_POLICIES)},
            "salary_min": {"type": ["integer", "null"]},
            "salary_max": {"type": ["integer", "null"]},
            "salary_currency": {"type": ["string", "null"]},
        },
        "required": ["skills", "remote_policy"],
    },
}

_ANTHROPIC_SYSTEM = (
    "You extract structured facts from a single job posting. Return skills as short "
    "lowercase tags. Only report a salary if the posting explicitly states one — never "
    "guess or infer. If no salary is stated, use null."
)


class AnthropicExtractor:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        import anthropic  # imported lazily so the dep is optional at runtime

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._fallback = HeuristicExtractor()

    def extract(self, job: JobRecord) -> ExtractionResult:
        prompt = (
            f"Title: {job.title}\nLocation: {job.location or 'n/a'}\n\n"
            f"Description:\n{(job.description_raw or '')[:6000]}"
        )
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=_ANTHROPIC_SYSTEM,
                tools=[_ANTHROPIC_TOOL],
                tool_choice={"type": "tool", "name": "record_job_facts"},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            # Never let extraction failure break ingestion; degrade to heuristic.
            return self._fallback.extract(job)

        data = None
        for block in msg.content:
            if getattr(block, "type", None) == "tool_use":
                data = block.input
                break
        if not data:
            return self._fallback.extract(job)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                return self._fallback.extract(job)

        remote = data.get("remote_policy", "unknown")
        if remote not in REMOTE_POLICIES:
            remote = "unknown"
        skills = canonicalize_skills(
            [str(s) for s in (data.get("skills") or []) if str(s).strip()]
        )
        # ATS structured comp wins if present; else use model's stated salary.
        smin = job.salary_min if job.salary_min is not None else data.get("salary_min")
        smax = job.salary_max if job.salary_max is not None else data.get("salary_max")
        scur = job.salary_currency or data.get("salary_currency")
        return ExtractionResult(
            skills=skills[:12],
            remote_policy=remote,
            salary_min=smin,
            salary_max=smax,
            salary_currency=scur,
        )


_DEEPSEEK_SYSTEM = (
    "You extract structured facts from ONE job posting and reply with a single JSON "
    "object and nothing else. Keys: "
    '"skills" (array of short lowercase technical tags, e.g. ["rust","k8s","rag","cuda"]; '
    "only genuinely required technical skills, not soft skills or the company's product "
    "names), "
    '"remote_policy" (one of "remote","hybrid","onsite","unknown"), '
    '"salary_min" (integer or null), "salary_max" (integer or null), '
    '"salary_currency" (ISO code string or null). '
    "Report a salary ONLY if the posting explicitly states one — never guess or infer. "
    "If unknown, use null."
)


ROLE_FAMILIES = ("engineering", "data", "product", "design", "marketing", "sales", "ops", "other")

_DEEPSEEK_ROLE_FAMILY_SYSTEM = (
    "Classify ONE job posting into exactly one job family and reply with a single JSON "
    'object and nothing else: {"role_family": "<value>"} where <value> is one of '
    "engineering, data, product, design, marketing, sales, ops, other. "
    "Judge by the ACTUAL function of the role, NOT keywords in the title. Critically: "
    "'Sales Engineer', 'Solutions Engineer', 'Solutions Architect', 'Solutions "
    "Consultant', 'Sales Development Representative', 'Account Executive', 'Account "
    "Manager', 'Engagement Manager', 'Customer Success' in a revenue / go-to-market / "
    "services-sales org are 'sales' — NOT 'engineering'. Software / platform / infra / "
    "backend / frontend / security / ML-systems engineering is 'engineering'. 'Data "
    "Engineer', 'ML Engineer', 'Data Scientist', 'Analytics' is 'data'. Product "
    "management is 'product'. Recruiting / HR / people / finance / legal / IT / support / "
    "operations is 'ops'. If genuinely unclear, use 'other'."
)


class DeepSeekExtractor:
    """OpenAI-compatible backend (default DeepSeek). Cheap model for a simple task.

    `extract_with_usage` returns token usage so the rebuild can track spend and stop at a
    budget ceiling. `extract` (the Extractor-interface method) degrades to the heuristic on
    any failure so live ingest never breaks.
    """

    name = "deepseek"

    def __init__(self, api_key: str, base_url: str, model: str, jd_char_cap: int = 4000):
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._cap = jd_char_cap
        self._fallback = HeuristicExtractor()
        self._client = None  # lazily-created pooled httpx.Client (keep-alive, thread-safe)

    def _http(self):
        if self._client is None:
            import httpx

            self._client = httpx.Client(
                timeout=httpx.Timeout(90.0, connect=10.0),
                limits=httpx.Limits(max_connections=64, max_keepalive_connections=64),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def _prompt(self, job: JobRecord) -> str:
        return (
            f"Title: {job.title}\nLocation: {job.location or 'n/a'}\n\n"
            f"Description:\n{(job.description_raw or '')[: self._cap]}"
        )

    def extract_with_usage(self, job: JobRecord) -> tuple[ExtractionResult, int, int]:
        """Raises on API/parse failure so callers can retry/track. Returns (result, in, out)."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _DEEPSEEK_SYSTEM},
                {"role": "user", "content": self._prompt(job)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 300,
            "stream": False,
        }
        resp = self._http().post(self._url, json=payload)
        resp.raise_for_status()
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)
        usage = body.get("usage", {})
        result = self._to_result(data, job)
        return result, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))

    def _to_result(self, data: dict, job: JobRecord) -> ExtractionResult:
        remote = data.get("remote_policy", "unknown")
        if remote not in REMOTE_POLICIES:
            remote = "unknown"
        skills = canonicalize_skills(
            [str(s) for s in (data.get("skills") or []) if str(s).strip()]
        )
        # ATS structured comp wins if present; else the model's stated salary.
        smin = job.salary_min if job.salary_min is not None else data.get("salary_min")
        smax = job.salary_max if job.salary_max is not None else data.get("salary_max")
        scur = job.salary_currency or data.get("salary_currency")
        return ExtractionResult(
            skills=skills[:12], remote_policy=remote,
            salary_min=smin, salary_max=smax, salary_currency=scur,
        )

    def extract(self, job: JobRecord) -> ExtractionResult:
        try:
            result, _, _ = self.extract_with_usage(job)
            return result
        except Exception:
            return self._fallback.extract(job)

    def classify_role_family_with_usage(self, job: JobRecord) -> tuple[str, int, int]:
        """Return (role_family, prompt_tokens, completion_tokens). Raises on failure."""
        prompt = (
            f"Title: {job.title}\nLocation: {job.location or 'n/a'}\n\n"
            f"Description:\n{(job.description_raw or '')[: min(self._cap, 2500)]}"
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _DEEPSEEK_ROLE_FAMILY_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 20,
            "stream": False,
        }
        resp = self._http().post(self._url, json=payload)
        resp.raise_for_status()
        body = resp.json()
        data = json.loads(body["choices"][0]["message"]["content"])
        label = str(data.get("role_family", "other")).strip().lower()
        if label not in ROLE_FAMILIES:
            label = "other"
        usage = body.get("usage", {})
        return label, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


def make_deepseek_extractor() -> "DeepSeekExtractor":
    if not config.DEEPSEEK_API_KEY:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set. Add it to .env (see README) before extracting."
        )
    return DeepSeekExtractor(
        config.DEEPSEEK_API_KEY,
        config.DEEPSEEK_BASE_URL,
        config.DEEPSEEK_MODEL,
        config.EXTRACTION_JD_CHAR_CAP,
    )


def get_extractor() -> Extractor:
    """Select the extractor from config. `auto` = DeepSeek→Anthropic if a key is set,
    else the offline heuristic."""
    choice = (config.EXTRACTOR or "auto").lower()
    if choice == "heuristic":
        return HeuristicExtractor()
    if choice in ("deepseek", "auto") and config.DEEPSEEK_API_KEY:
        try:
            return make_deepseek_extractor()
        except Exception:
            pass
    if choice in ("anthropic", "auto") and config.ANTHROPIC_API_KEY:
        try:
            return AnthropicExtractor(config.ANTHROPIC_API_KEY, config.EXTRACTION_MODEL)
        except Exception:
            return HeuristicExtractor()
    return HeuristicExtractor()
