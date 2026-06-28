"""Central configuration for the Mutual Fund FAQ Assistant.

Loads settings from the environment (`.env`) and exposes resolved filesystem
paths and the curated corpus (`corpus/sources.yaml`). Import `settings` and
`SCHEMES` / `EDU_LINKS` elsewhere rather than re-reading these files.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Filesystem layout (all relative to this file) -------------------------
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CHROMA_DIR = DATA_DIR / "chroma"
FACTS_DB = DATA_DIR / "facts.db"
CORPUS_FILE = ROOT_DIR / "corpus" / "sources.yaml"


class Settings(BaseSettings):
    """Environment-backed settings (see `.env.example`)."""

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="", alias="ANTHROPIC_MODEL")
    embed_model: str = Field(
        default="BAAI/bge-small-en-v1.5", alias="EMBED_MODEL"
    )

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_dirs() -> None:
    """Create data directories needed by the ingestion/query pipelines."""
    for d in (DATA_DIR, RAW_DIR, CHROMA_DIR):
        d.mkdir(parents=True, exist_ok=True)


@lru_cache
def _load_corpus() -> dict[str, Any]:
    with CORPUS_FILE.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_schemes() -> list[dict[str, str]]:
    """The 5 curated Groww pages to ingest."""
    return _load_corpus().get("schemes", [])


def get_edu_links() -> dict[str, str]:
    """AMFI/SEBI educational links used in refusals (never indexed)."""
    return _load_corpus().get("edu_links", {})


# Convenience module-level handles
settings = get_settings()
SCHEMES = get_schemes()
EDU_LINKS = get_edu_links()
CORPUS_URLS = {s["url"] for s in SCHEMES}  # citation allowlist


if __name__ == "__main__":
    # Quick self-check: `python config.py`
    ensure_dirs()
    print(f"Root:        {ROOT_DIR}")
    print(f"Embed model: {settings.embed_model}")
    print(f"LLM model:   {settings.anthropic_model or '<unset>'}")
    print(f"API key set: {bool(settings.anthropic_api_key)}")
    print(f"Schemes:     {len(SCHEMES)}")
    for s in SCHEMES:
        print(f"  - {s['scheme_id']}: {s['name']}")
    print(f"Edu links:   {list(EDU_LINKS)}")
