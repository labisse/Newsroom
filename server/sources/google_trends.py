"""Google Trends via SerpAPI.

Port de gnewsalyzer V2 / google_trends.php (fonction fetch_trends_from_api).

SerpAPI expose 3 fenêtres temporelles pour `google_trends_trending_now` :
  - actuelles      → pas de paramètre `time`
  - 48 dernières h → time=past_48_hours
  - 7 derniers j   → time=past_7_days

Endpoint : https://serpapi.com/search
Doc       : https://serpapi.com/google-trends-trending-now-api

La clé doit être placée dans SERPAPI_KEY (.env).
"""

from __future__ import annotations

from typing import Any

import requests

from server.config import settings
from server.sources._common import now_iso, today_str, write_snapshot

ENDPOINT = "https://serpapi.com/search"
TIMEOUT_S = 30
SOURCE_KEY = "google_trends"

WINDOWS: dict[str, str | None] = {
    "current": None,
    "48h": "past_48_hours",
    "weekly": "past_7_days",
}


def _normalize_traffic(raw: Any) -> int:
    """Convertit '50K+' / '1M+' / 50000 / None → int (search_volume)."""
    if raw is None:
        return 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        cleaned = raw.replace("+", "").strip()
        if cleaned.endswith("M"):
            return int(float(cleaned[:-1]) * 1_000_000)
        if cleaned.endswith("K"):
            return int(float(cleaned[:-1]) * 1_000)
        try:
            return int(cleaned)
        except ValueError:
            return 0
    return 0


def _format_trends(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise les deux formats de réponse possibles."""
    formatted: list[dict[str, Any]] = []

    # Format ancien : trending_searches[]
    if "trending_searches" in data and isinstance(data["trending_searches"], list):
        for trend in data["trending_searches"]:
            if isinstance(trend, dict):
                query = trend.get("query") or trend.get("title") or "Tendance"
                volume = (
                    trend.get("search_volume")
                    if "search_volume" in trend
                    else _normalize_traffic(trend.get("traffic"))
                )
                formatted.append(
                    {
                        "query": query,
                        "search_volume": volume,
                        "percentage_increase": trend.get("percentage_increase"),
                        "categories": trend.get("categories"),
                    }
                )
            elif isinstance(trend, str):
                formatted.append({"query": trend, "search_volume": 0})
        return formatted

    # Format actuel : trends[]
    if "trends" in data and isinstance(data["trends"], list):
        for trend in data["trends"]:
            if not isinstance(trend, dict):
                continue
            volume = (
                trend.get("search_volume")
                if "search_volume" in trend
                else _normalize_traffic(trend.get("traffic"))
            )
            formatted.append(
                {
                    "query": trend.get("query", ""),
                    "search_volume": volume,
                    "percentage_increase": trend.get("percentage_increase"),
                    "categories": trend.get("categories"),
                }
            )
        return formatted

    return formatted


def fetch_window(window: str, geo: str | None = None) -> list[dict[str, Any]]:
    """Récupère les trends pour une fenêtre donnée (current/48h/weekly)."""
    if not settings.serpapi_key:
        raise RuntimeError("SERPAPI_KEY manquant dans .env")
    if window not in WINDOWS:
        raise ValueError(f"window invalide: {window}. Choisir parmi {list(WINDOWS)}")

    params: dict[str, Any] = {
        "engine": "google_trends_trending_now",
        "geo": geo or settings.serpapi_geo,
        "api_key": settings.serpapi_key,
    }
    time_param = WINDOWS[window]
    if time_param:
        params["time"] = time_param

    response = requests.get(ENDPOINT, params=params, timeout=TIMEOUT_S)
    response.raise_for_status()
    return _format_trends(response.json())


def fetch() -> dict[str, Any]:
    """Récupère les 3 fenêtres et retourne un payload agrégé."""
    windows_data = {key: fetch_window(key) for key in WINDOWS}

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "geo": settings.serpapi_geo,
        "windows": {
            key: {"count": len(trends), "trends": trends}
            for key, trends in windows_data.items()
        },
    }


def run() -> dict[str, Any]:
    payload = fetch()
    write_snapshot(SOURCE_KEY, payload, today_str())
    return payload
