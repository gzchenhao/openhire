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
import threading
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


# --- free, deterministic role_family fallback ---------------------------------
# The DeepSeek classifier above is the quality path, but it costs money and only runs on
# demand — so jobs ingested between passes sit at role_family NULL, which makes them
# invisible to `--role-family` (the filter matches on the value, not on NULL). This
# keyword classifier fills that gap for free. It is deliberately CONSERVATIVE: it returns
# None whenever it is not confident, leaving the row NULL so the DeepSeek pass (which
# resumes on `role_family IS NULL`) can still claim it later.
#
# Order matters. The sales patterns are checked first because the exact trap the DeepSeek
# prompt calls out — 售前/解决方案/客户成功 "engineers" in a revenue org — is a sales role
# whose title contains 工程师.
_RF_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sales", (
        "销售", "客户经理", "大客户", "商务", "渠道", "售前", "解决方案工程师",
        "解决方案专家", "客户成功", "业务拓展",
        "account executive", "account manager", "sales", "business development",
        "solutions engineer", "solutions architect", "customer success", "presales",
    )),
    ("data", (
        "数据工程", "数据分析", "数据科学", "数据挖掘", "大数据", "数据仓库", "商业分析",
        "data engineer", "data scientist", "data analyst", "analytics", "bi ",
    )),
    ("design", (
        "设计师", "交互设计", "视觉设计", "工业设计", "用户体验",
        "designer", "ux ", "ui ",
    )),
    ("product", ("产品经理", "产品总监", "产品专员", "product manager", "product owner")),
    ("marketing", (
        "市场营销", "市场推广", "品牌", "公关", "内容运营", "新媒体",
        "marketing", "brand", "public relations",
    )),
    ("ops", (
        "人力资源", "招聘", "行政", "财务", "法务", "供应链", "采购", "生产", "制造",
        "质量", "品质", "仓储", "物流", "运维", "客服", "职能",
        "recruiter", "human resources", "finance", "legal", "procurement",
        "supply chain", "manufacturing", "quality", "operations manager", "it support",
    )),
    ("engineering", (
        "工程师", "研发", "开发", "算法", "架构师", "嵌入式", "软件", "硬件", "电气",
        "机械", "结构", "测试", "仿真", "感知", "定位", "规划控制", "标定", "视觉",
        "engineer", "developer", "programmer", "architect", "scientist", "research",
    )),
)


def classify_role_family_heuristic(title: str, description: str = "") -> str | None:
    """Best-effort job family from the title alone, or None when unsure.

    Title-only by design: Chinese JD bodies are boilerplate-heavy (公司介绍/福利) and match
    far too many families, so the body is used only as a tiebreak-free fallback signal.
    """
    blob = f" {(title or '').lower()} "
    if not blob.strip():
        return None
    for family, needles in _RF_RULES:
        if any(n in blob for n in needles):
            return family
    return None


class RateLimited(RuntimeError):
    """HTTP 429 from the provider. Raised so callers can back off instead of retrying hot."""


_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


def parse_json_object(content: str) -> dict:
    """Parse a model reply that should be one JSON object.

    Providers differ: DeepSeek honours `response_format=json_object` and returns bare
    JSON, while GLM (with thinking disabled) wraps it in a ```json fence. Strip the
    fence, then fall back to the first balanced-looking {...} span.
    """
    text = (content or "").strip()
    text = _JSON_FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")
    return data


class DeepSeekExtractor:
    """OpenAI-compatible backend (default DeepSeek). Cheap model for a simple task.

    `extract_with_usage` returns token usage so the rebuild can track spend and stop at a
    budget ceiling. `extract` (the Extractor-interface method) degrades to the heuristic on
    any failure so live ingest never breaks.
    """

    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        jd_char_cap: int = 4000,
        *,
        max_tokens: int = 300,
        rf_max_tokens: int = 20,
        json_mode: bool = True,
        extra_body: dict | None = None,
    ):
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._cap = jd_char_cap
        self._max_tokens = max_tokens
        self._rf_max_tokens = rf_max_tokens
        self._json_mode = json_mode
        self._extra_body = dict(extra_body or {})
        self._fallback = HeuristicExtractor()
        self._client = None  # lazily-created pooled httpx.Client (keep-alive, thread-safe)

    def _payload(self, system: str, prompt: str, max_tokens: int) -> dict:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
            **self._extra_body,
        }
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _call(self, payload: dict) -> dict:
        """POST once. Raises RateLimited on 429 so the caller can back off."""
        resp = self._http().post(self._url, json=payload)
        if resp.status_code == 429:
            raise RateLimited("HTTP 429 from provider")
        resp.raise_for_status()
        return resp.json()

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
        body = self._call(
            self._payload(_DEEPSEEK_SYSTEM, self._prompt(job), self._max_tokens)
        )
        data = parse_json_object(body["choices"][0]["message"]["content"])
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
        body = self._call(
            self._payload(_DEEPSEEK_ROLE_FAMILY_SYSTEM, prompt, self._rf_max_tokens)
        )
        data = parse_json_object(body["choices"][0]["message"]["content"])
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


class GLMExtractor(DeepSeekExtractor):
    """Zhipu GLM via the OpenAI-compatible *coding-plan* endpoint.

    Same wire protocol as DeepSeek, three provider-specific adjustments:
      * `thinking: {enabled, effort: low}` — the glm-5.3 family reasons before
        answering by default (~240 reasoning tokens on a task that needs none).
        `disabled` worked until 2026-08-31, when the endpoint began rejecting it
        (400/1210: only low/high/max allowed); effort:low measured 62 reasoning
        tokens. On any future 1210 the extractor drops the parameter entirely.
      * `max_tokens` ≥ 1024 — reasoning tokens are charged against max_tokens BEFORE any
        content is emitted, so a small cap returns an empty string rather than an error.
        The floor keeps extraction safe even if `thinking` is ever ignored.
      * no `response_format` — the coding endpoint accepts it, but with thinking off the
        reply can still arrive inside a ```json fence, so `parse_json_object` (which
        strips fences) is the real guarantee and the extra prompt tokens buy nothing.

    Cash cost is zero: tokens are metered by the prepaid coding plan, not billed per call.
    Rows written by this backend are stamped `extraction_source='glm'` — never 'deepseek'.

    Accepts one key or a try-order list. Coding-plan quotas are per-key, so when the
    active key is spent (HTTP 429 / provider code 1310) or invalid (HTTP 401) the
    extractor hot-swaps to the next key mid-run and retries the same request; only when
    every key is dead does it raise `RateLimited`, which lands the resumable rebuild on
    its normal breakpoint. A plain 429 (transient rate limit, not 1310) never rotates —
    that is what the caller's backoff is for.
    """

    name = "glm"

    def __init__(
        self, api_key: str | list, base_url: str, model: str, jd_char_cap: int = 4000
    ):
        # Normalise to (key, base_url, model) triples: keys are NOT interchangeable —
        # a coding-plan key and a token-billed resource-pack key live on different
        # endpoints and cover different models, so each entry carries its own pair.
        # Accepted inputs: one key string, a list of key strings (all sharing the
        # constructor's base_url/model), or a list of (key, base_url, model) triples
        # (e.g. config.ZhipuKey) with falsy members falling back to the constructor's.
        entries: list[tuple[str, str, str]] = []
        items = [api_key] if isinstance(api_key, str) else list(api_key)
        for item in items:
            if isinstance(item, str):
                k, b, m = item, base_url, model
            else:
                k, b, m = item
            if k and k.strip():
                entries.append((k.strip(), (b or base_url), (m or model)))
        if not entries:
            raise RuntimeError("GLMExtractor needs at least one API key")
        self._keys = entries
        self._key_idx = 0
        self._key_lock = threading.Lock()
        k0, b0, m0 = entries[0]
        super().__init__(
            k0,
            b0,
            m0,
            jd_char_cap,
            max_tokens=1024,
            rf_max_tokens=1024,
            json_mode=False,
            # 2026-08-31: the coding endpoint stopped accepting {"type": "disabled"}
            # (HTTP 400, code 1210 — "不支持关闭思考，请使用 low、high 或 max").
            # effort:low measured 62 reasoning tokens vs 78 with thinking omitted.
            # If the provider changes the contract again, _call self-heals by dropping
            # the parameter entirely on the first 1210 — omission is always accepted.
            extra_body={"thinking": {"type": "enabled", "effort": "low"}},
        )

    @staticmethod
    def _provider_code(resp) -> str:
        """Zhipu error codes arrive either top-level or under `error`."""
        try:
            body = resp.json()
        except Exception:
            return ""
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        return str(err.get("code", ""))

    def _rotate_from(self, failed_idx: int) -> bool:
        """Swap to the next key (and ITS endpoint+model). True = retry is worthwhile."""
        with self._key_lock:
            if failed_idx != self._key_idx:
                return True  # another worker already rotated; just retry on the new key
            if self._key_idx + 1 >= len(self._keys):
                return False
            self._key_idx += 1
            key, base, model = self._keys[self._key_idx]
            self._api_key = key
            self._url = base.rstrip("/") + "/chat/completions"
            self._model = model
            # Abandon (do not close) the old client: other workers may be mid-request
            # on it. At most len(keys) clients ever exist, so the leak is bounded.
            self._client = None
            return True

    def _http(self):
        client = self._client
        if client is None:
            with self._key_lock:
                client = super()._http()
        return client

    def _call(self, payload: dict) -> dict:
        stripped_thinking = False
        for _ in range(len(self._keys) + 2):
            idx = self._key_idx
            # The retried request must name the CURRENT key's model — payloads are
            # built before _call, so after a rotation the model may have changed.
            if payload.get("model") != self._model:
                payload = {**payload, "model": self._model}
            resp = self._http().post(self._url, json=payload)
            if (
                resp.status_code == 400
                and not stripped_thinking
                and "thinking" in payload
                and self._provider_code(resp) == "1210"
            ):
                # The provider changed the thinking-parameter contract (again). Drop
                # the parameter — omission is always accepted — and stop sending it
                # for the rest of this extractor's life.
                stripped_thinking = True
                self._extra_body.pop("thinking", None)
                payload = {k: v for k, v in payload.items() if k != "thinking"}
                continue
            if resp.status_code in (401, 429):
                code = self._provider_code(resp)
                # Dead-key signals seen live: 401 invalid; 1310 quota exhausted; 1113
                # "no resource pack" — a key whose pack is fully consumed FLIPS from
                # 1310 to 1113 mid-run (observed 2026-08-31 on key #3), so both mean
                # "rotate", not "back off".
                key_dead = resp.status_code == 401 or code in ("1310", "1113")
                if key_dead:
                    if self._rotate_from(idx):
                        continue
                    raise RateLimited(
                        f"every configured GLM key is exhausted or invalid "
                        f"(last: HTTP {resp.status_code}, code {code or 'n/a'})"
                    )
                raise RateLimited(f"HTTP 429 from provider (code {code or 'n/a'})")
            resp.raise_for_status()
            return resp.json()
        raise RateLimited("GLM key rotation exceeded its retry budget")


def make_glm_extractor(model: str | None = None) -> "GLMExtractor":
    if not config.ZHIPU_API_KEY:
        raise RuntimeError(
            "ZHIPU_API_KEY is not set. Add it to .env (see README) before extracting."
        )
    entries = config.zhipu_api_keys()
    if model:  # an explicit model override applies to the primary key only; numbered
        # slots keep their own ZHIPU_API_KEY_N_MODEL — their packs cover what they cover.
        entries = [entries[0]._replace(model=model)] + entries[1:]
    return GLMExtractor(
        entries,
        config.GLM_BASE_URL,
        model or config.GLM_MODEL,
        config.EXTRACTION_JD_CHAR_CAP,
    )


# Backends that write real LLM-quality extraction. A row already stamped with any of
# these is NOT re-extracted by another one — glm and deepseek must not churn each other.
LLM_SOURCES = ("deepseek", "glm", "anthropic")


def make_llm_extractor(backend: str = "deepseek", model: str | None = None):
    """Factory used by the rebuild pipeline. Returns (extractor, source_label)."""
    b = (backend or "deepseek").lower()
    if b == "deepseek":
        return make_deepseek_extractor()
    if b in ("glm", "glm-flash", "glm-5.3", "glm-5.3-flash"):
        if model is None and b not in ("glm",):
            model = {"glm-flash": "glm-5.3-flash"}.get(b, b)
        return make_glm_extractor(model)
    raise RuntimeError(f"unknown extraction backend: {backend!r}")


def get_extractor() -> Extractor:
    """Select the extractor from config.

    `auto` prefers GLM: its tokens come out of a prepaid coding plan, so live ingest
    costs no cash, whereas DeepSeek bills per call — an unattended `ohp ingest` should
    never quietly start spending. Falls through to DeepSeek, then Anthropic, then the
    offline heuristic. Every LLM path degrades to the heuristic on failure (including a
    spent quota), so ingestion never breaks on the extractor.
    """
    choice = (config.EXTRACTOR or "auto").lower()
    if choice == "heuristic":
        return HeuristicExtractor()
    if choice in ("glm", "auto") and config.ZHIPU_API_KEY:
        try:
            return make_glm_extractor()
        except Exception:
            pass
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
