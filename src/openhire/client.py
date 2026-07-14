"""Client-side state — lives entirely under ~/.openhire, never on the server.

  fingerprint.json   anonymous id + locally-derived skills (from `ohp init --scan`)
  receipts.jsonl     append-only log of applications you authorized

Red line #1: your code and identity never leave the machine. `ohp init --scan` reads a
local repo to derive skill TAGS only — file contents are never transmitted or stored.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import secrets
from collections import Counter
from pathlib import Path

from . import config
from .pipeline.extract import canonicalize_skills

FINGERPRINT_FILE = "fingerprint.json"
RECEIPTS_FILE = "receipts.jsonl"


def _home() -> Path:
    return config.ensure_client_home()


def fingerprint_path() -> Path:
    return _home() / FINGERPRINT_FILE


def receipts_path() -> Path:
    return _home() / RECEIPTS_FILE


@dataclasses.dataclass
class Fingerprint:
    id: str  # anonymous, e.g. "#a3f9"
    skills: list[str] = dataclasses.field(default_factory=list)
    language_pct: dict[str, float] = dataclasses.field(default_factory=dict)
    repos_scanned: int = 0
    created_at: str = ""

    def to_json(self) -> dict:
        return dataclasses.asdict(self)


def new_fingerprint_id() -> str:
    return "#" + secrets.token_hex(2)  # e.g. #a3f9


def load_fingerprint() -> Fingerprint | None:
    p = fingerprint_path()
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return Fingerprint(
        id=data["id"],
        skills=data.get("skills", []),
        language_pct=data.get("language_pct", {}),
        repos_scanned=data.get("repos_scanned", 0),
        created_at=data.get("created_at", ""),
    )


def save_fingerprint(fp: Fingerprint) -> Path:
    p = fingerprint_path()
    p.write_text(json.dumps(fp.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_or_create_fingerprint() -> Fingerprint:
    """Return the saved fingerprint, or mint a bare anonymous one (id only)."""
    fp = load_fingerprint()
    if fp is None:
        fp = Fingerprint(
            id=new_fingerprint_id(),
            created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        save_fingerprint(fp)
    return fp


def append_receipt(receipt: dict) -> None:
    with receipts_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(receipt, ensure_ascii=False) + "\n")


def load_receipts() -> list[dict]:
    p = receipts_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# --- local repo scan (code never leaves the machine) -------------------------
_EXT_LANG = {
    ".py": "python", ".rs": "rust", ".go": "go", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".java": "java", ".rb": "ruby",
    ".scala": "scala", ".kt": "kotlin", ".swift": "swift", ".cpp": "c++", ".cc": "c++",
    ".cxx": "c++", ".c": "c", ".ex": "elixir", ".exs": "elixir", ".cu": "cuda",
    ".sql": "sql",
}

# Dependency name substrings → skill tag (canonicalized downstream).
_DEP_SKILL = {
    "torch": "pytorch", "pytorch": "pytorch", "tensorflow": "tensorflow", "jax": "jax",
    "langchain": "rag", "llama-index": "rag", "llama_index": "rag", "chromadb": "vector-db",
    "pinecone": "vector-db", "weaviate": "vector-db", "qdrant": "vector-db",
    "faiss": "vector-db", "transformers": "transformers", "vllm": "llm", "openai": "llm",
    "anthropic": "llm", "fastapi": "python", "django": "python", "flask": "python",
    "react": "react", "next": "react", "express": "node", "kubernetes": "k8s",
    "kubernetes-client": "k8s", "boto3": "aws", "aws-sdk": "aws", "google-cloud": "gcp",
    "azure": "azure", "kafka": "kafka", "pyspark": "spark", "airflow": "airflow",
    "grpcio": "grpc", "grpc": "grpc", "graphql": "graphql", "tokio": "rust",
    "redis": "redis", "psycopg": "postgres", "sqlalchemy": "sql",
}

_SKIP_DIRS = {".git", "node_modules", "target", "dist", "build", ".venv", "venv",
              "__pycache__", ".next", ".mypy_cache", ".pytest_cache", "vendor"}


def scan_repos(root: Path, max_files: int = 20000) -> tuple[list[str], dict[str, float], int]:
    """Derive skill tags + language percentages from a local directory.

    Returns (skills, language_pct, repos_scanned). Only tags are produced — no file
    content ever leaves this function.
    """
    root = Path(root).expanduser()
    lang_counts: Counter[str] = Counter()
    dep_skills: set[str] = set()
    repos: set[str] = set()
    seen = 0

    for path in root.rglob("*"):
        if seen >= max_files:
            break
        if path.is_dir():
            continue
        parts = set(path.parts)
        if parts & _SKIP_DIRS:
            continue
        seen += 1
        name = path.name.lower()
        suffix = path.suffix.lower()

        if suffix in _EXT_LANG:
            lang_counts[_EXT_LANG[suffix]] += 1

        # Mark the repo (first-level dir under root) as a scanned project.
        try:
            rel = path.relative_to(root)
            if len(rel.parts) > 1:
                repos.add(rel.parts[0])
        except ValueError:
            pass

        # Manifests → dependency-derived skills.
        if name in ("package.json", "requirements.txt", "pyproject.toml", "cargo.toml",
                    "go.mod", "pom.xml", "build.gradle"):
            dep_skills |= _skills_from_manifest(path, name)
        if name == "dockerfile" or suffix == ".tf":
            dep_skills.add("docker" if name == "dockerfile" else "terraform")

    total_lang = sum(lang_counts.values()) or 1
    language_pct = {
        lang: round(cnt / total_lang * 100, 1)
        for lang, cnt in lang_counts.most_common()
    }
    # Skills = prominent languages (>= 5%) + dependency-derived tags.
    lang_skills = [lang for lang, pct in language_pct.items() if pct >= 5.0]
    skills = canonicalize_skills(lang_skills + sorted(dep_skills))
    return skills, language_pct, len(repos) or (1 if seen else 0)


def _skills_from_manifest(path: Path, name: str) -> set[str]:
    out: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return out
    for dep, skill in _DEP_SKILL.items():
        if dep in text:
            out.add(skill)
    return out
