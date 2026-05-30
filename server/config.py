"""Configuration centralisée — charge les variables d'environnement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# override=True : si une variable d'environnement existe déjà dans le shell
# (ex. via ~/.zshrc) avec une valeur vide ou obsolète, on laisse .env gagner.
# Sans ça, ANTHROPIC_API_KEY="" exporté ailleurs masquerait silencieusement
# la clé du .env (bug rencontré en prod).
load_dotenv(ROOT / ".env", override=True)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _get_int(key: str, default: int) -> int:
    raw = _get(key)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # MSN
    msn_api_key: str = _get("MSN_API_KEY")
    msn_market: str = _get("MSN_MARKET", "fr-fr")
    msn_limit: int = _get_int("MSN_LIMIT", 100)

    # SerpAPI (Google Trends)
    serpapi_key: str = _get("SERPAPI_KEY")
    serpapi_geo: str = _get("SERPAPI_GEO", "FR")

    # Wikimedia
    wikimedia_user_agent: str = _get(
        "WIKIMEDIA_USER_AGENT",
        "EditorialSignal/0.1 (https://github.com/labisse/Newsroom; contact@example.com)",
    )
    wikimedia_project: str = _get("WIKIMEDIA_PROJECT", "fr.wikipedia")

    # X Trends (scraping)
    x_trends_url: str = _get("X_TRENDS_URL", "https://trends24.in/france/")

    # Discoversnoop (Google Discover visibility export)
    discoversnoop_email: str = _get("DISCOVERSNOOP_EMAIL")
    discoversnoop_password: str = _get("DISCOVERSNOOP_PASSWORD")
    discoversnoop_country: str = _get("DISCOVERSNOOP_COUNTRY", "FR")
    discoversnoop_hours: int = _get_int("DISCOVERSNOOP_HOURS", 12)

    # Google Search Console (OAuth2 par projet)
    gsc_client_id: str = _get("GSC_CLIENT_ID")
    gsc_client_secret: str = _get("GSC_CLIENT_SECRET")
    gsc_redirect_uri: str = _get(
        "GSC_REDIRECT_URI", "http://localhost:8765/callback"
    )
    gsc_callback_port: int = _get_int("GSC_CALLBACK_PORT", 8765)

    # Embeddings (RAG sémantique)
    voyage_api_key: str = _get("VOYAGE_API_KEY")
    voyage_model: str = _get("VOYAGE_MODEL", "voyage-3")

    # Claude — génération de titres dans le style d'un média
    anthropic_api_key: str = _get("ANTHROPIC_API_KEY")
    anthropic_model: str = _get("ANTHROPIC_MODEL", "claude-haiku-4-5")

    # YouTube Data API v3 — trending FR
    youtube_api_key: str = _get("YOUTUBE_API_KEY")
    youtube_region: str = _get("YOUTUBE_REGION", "FR")

    # Reddit OAuth (script app) — fallback RSS si vide
    reddit_client_id: str = _get("REDDIT_CLIENT_ID")
    reddit_client_secret: str = _get("REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = _get(
        "REDDIT_USER_AGENT",
        "EditorialSignal/1.0 by /u/editorial_signal_bot",
    )

    # PostgreSQL time-series storage (DigitalOcean Managed Postgres)
    # Vide = storage désactivé (le pipeline continue sans logger en DB)
    database_url: str = _get("DATABASE_URL")


settings = Settings()
