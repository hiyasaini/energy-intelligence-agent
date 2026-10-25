"""Runtime configuration, read from environment / .env. No company-specific settings live here."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is a declared dependency, but keep import failure non-fatal
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(ROOT / ".env", override=False)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: os.getenv("EIA_DB_PATH", str(ROOT / "data" / "eia.sqlite")))
    cache_dir: str = field(default_factory=lambda: os.getenv("EIA_CACHE_DIR", str(ROOT / "data" / "cache")))

    # Providers: search = tavily | serper | brave | anthropic | duckduckgo | none
    search_provider: str = field(default_factory=lambda: os.getenv("EIA_SEARCH_PROVIDER", "none").lower())
    # llm = anthropic | openai | none   (openai = any OpenAI-compatible endpoint)
    llm_provider: str = field(default_factory=lambda: os.getenv("EIA_LLM_PROVIDER", "none").lower())

    tavily_api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    serper_api_key: str = field(default_factory=lambda: os.getenv("SERPER_API_KEY", ""))
    brave_api_key: str = field(default_factory=lambda: os.getenv("BRAVE_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    direct_sources: bool = field(default_factory=lambda: os.getenv("EIA_DIRECT_SOURCES", "on").lower()
                                 not in ("off", "none", "false", "0"))
    peers: int = field(default_factory=lambda: _int("EIA_PEERS", 3))   # 0 turns the peer comparison off
    max_rounds: int = field(default_factory=lambda: _int("EIA_MAX_ROUNDS", 3))
    max_sources_per_round: int = field(default_factory=lambda: _int("EIA_MAX_SOURCES_PER_ROUND", 8))
    max_pdf_pages: int = field(default_factory=lambda: _int("EIA_MAX_PDF_PAGES", 350))
    http_timeout: int = field(default_factory=lambda: _int("EIA_HTTP_TIMEOUT", 25))
    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "EIA_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        )
    )

    def describe(self) -> dict:
        """Safe summary for display (never exposes keys)."""
        return {
            "search_provider": self.search_provider,
            "llm_provider": self.llm_provider,
            "max_rounds": self.max_rounds,
            "max_sources_per_round": self.max_sources_per_round,
            "direct_sources": self.direct_sources,
            "peers": self.peers,
            "keys_present": {
                "TAVILY_API_KEY": bool(self.tavily_api_key),
                "SERPER_API_KEY": bool(self.serper_api_key),
                "BRAVE_API_KEY": bool(self.brave_api_key),
                "ANTHROPIC_API_KEY": bool(self.anthropic_api_key),
                "OPENAI_API_KEY": bool(self.openai_api_key),
            },
        }


def get_settings(**overrides) -> Settings:
    s = Settings()
    for k, v in overrides.items():
        if v is not None and hasattr(s, k):
            setattr(s, k, v)
    return s
