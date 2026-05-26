"""Wikimedia Pageviews fetcher.

Port de gnewsalyzer V2 / wiki_fetch_and_analyze.php.

API REST officielle Wikimedia :
  https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{project}/all-access/YYYY/MM/DD

Les données du jour J ne sont disponibles qu'à partir de J+1 — on
récupère toujours « hier » comme dans la version PHP.

Pas d'auth, juste un User-Agent identifiable demandé par la doc
Wikimedia (cf. https://www.mediawiki.org/wiki/API:Etiquette).
"""

from __future__ import annotations

from typing import Any

import requests

from server.config import settings
from server.sources._common import (
    now_iso,
    today_str,
    write_snapshot,
    yesterday_path_parts,
)

API_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top"
TIMEOUT_S = 30
SOURCE_KEY = "wikimedia"

# Préfixes de pages spéciales à exclure (équivalent du filter_articles PHP)
EXCLUDED_PREFIXES = (
    "Spécial:",
    "Wikipédia:",
    "Catégorie:",
    "Fichier:",
    "Modèle:",
    "Aide:",
    "Portail:",
    "Discussion:",
    "Utilisateur:",
    "Projet:",
    # Variantes anglaises au cas où le projet serait en.wikipedia
    "Special:",
    "Wikipedia:",
    "Category:",
    "File:",
    "Template:",
    "Help:",
    "Portal:",
    "Talk:",
    "User:",
)


def _is_excluded(title: str) -> bool:
    return any(title.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def fetch(project: str | None = None) -> dict[str, Any]:
    """Récupère le top pageviews de la veille.

    Args:
        project: ex. "fr.wikipedia" (par défaut: settings.wikimedia_project).
    """
    project = project or settings.wikimedia_project
    date_str, formatted_date = yesterday_path_parts()
    url = f"{API_BASE}/{project}/all-access/{formatted_date}"

    headers = {
        "User-Agent": settings.wikimedia_user_agent,
        "Accept": "application/json",
    }

    response = requests.get(url, headers=headers, timeout=TIMEOUT_S)
    response.raise_for_status()
    data = response.json()

    items = data.get("items") or []
    if not items or "articles" not in items[0]:
        raise RuntimeError("Format Wikimedia inattendu : pas de items[0].articles")

    raw_articles = items[0]["articles"]
    filtered = [
        {
            "rank": a.get("rank"),
            "article": a.get("article", ""),
            "title_display": (a.get("article") or "").replace("_", " "),
            "views": int(a.get("views", 0) or 0),
        }
        for a in raw_articles
        if isinstance(a, dict) and not _is_excluded(a.get("article", ""))
    ]

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "project": project,
        "date": date_str,
        "count": len(filtered),
        "articles": filtered,
    }


def run() -> dict[str, Any]:
    payload = fetch()
    write_snapshot(SOURCE_KEY, payload, today_str())
    return payload
