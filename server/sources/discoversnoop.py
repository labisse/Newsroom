"""Discoversnoop fetcher.

discoversnoop.com expose un export CSV authentifié des "live pages"
Google Discover par pays. Le CSV contient pour chaque article :
url, title, publisher, snippet, score (visibilité Discover), position,
category, firstviewed/lastviewed, entities (entités nommées), etc.

Le `score` Discover est le signal le plus pertinent qu'on ait pour
le produit (objectif final = optimiser pour Google Discover).

Auth : form POST classique sur /login (email + password). La session
PHPSESSID est gardée par `requests.Session` pour les requêtes suivantes.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import requests

from server.config import settings
from server.sources._common import now_iso, today_str, write_snapshot

BASE_URL = "https://app.discoversnoop.com"
LOGIN_URL = f"{BASE_URL}/login"
EXPORT_URL = f"{BASE_URL}/export"

TIMEOUT_S = 30
SOURCE_KEY = "discoversnoop"

# Colonnes qu'on veut typer/convertir
INT_COLS = ("position", "is_new", "is_headline", "is_short", "is_showcase", "is_video", "is_webstory")
FLOAT_COLS = ("score",)


def _login(session: requests.Session, email: str, password: str) -> None:
    """Authentifie la session contre /login.

    Lève RuntimeError si l'auth échoue. L'app discoversnoop redirige
    vers / en cas de succès. En cas d'échec elle reste sur /login.
    """
    # 1. GET initial pour récupérer un éventuel cookie de session
    session.get(BASE_URL + "/", timeout=TIMEOUT_S, allow_redirects=True)

    # 2. POST des credentials
    response = session.post(
        LOGIN_URL,
        data={"email": email, "password": password, "origin": "/"},
        timeout=TIMEOUT_S,
        allow_redirects=True,
    )
    response.raise_for_status()

    # Heuristique d'échec : si on est toujours sur /login après le POST,
    # c'est que l'auth a échoué.
    final = response.url or ""
    if "/login" in final:
        raise RuntimeError(
            "Authentification Discoversnoop échouée — vérifie "
            "DISCOVERSNOOP_EMAIL et DISCOVERSNOOP_PASSWORD dans .env"
        )


def _parse_csv(text: str) -> list[dict[str, Any]]:
    """Parse le CSV en list[dict], avec typage des colonnes numériques."""
    reader = csv.DictReader(io.StringIO(text))
    articles: list[dict[str, Any]] = []

    for row in reader:
        # Conversions numériques douces (silencieuses sur erreur)
        for col in INT_COLS:
            raw = row.get(col)
            if raw is None or raw == "":
                row[col] = None
            else:
                try:
                    row[col] = int(raw)
                except ValueError:
                    row[col] = None

        for col in FLOAT_COLS:
            raw = row.get(col)
            if raw is None or raw == "":
                row[col] = None
            else:
                try:
                    row[col] = float(raw)
                except ValueError:
                    row[col] = None

        # entities : "Pierre Deny, Okaïdi" → liste de strings
        ent_raw = row.get("entities") or ""
        row["entities_list"] = [
            e.strip() for e in ent_raw.split(",") if e.strip()
        ]

        articles.append(row)

    return articles


def fetch(
    *,
    country: str = "FR",
    hours: int = 12,
    only_new: int = 1,
) -> dict[str, Any]:
    """Récupère l'export CSV Discoversnoop pour le pays / fenêtre donnés."""
    if not settings.discoversnoop_email or not settings.discoversnoop_password:
        raise RuntimeError(
            "DISCOVERSNOOP_EMAIL ou DISCOVERSNOOP_PASSWORD manquant dans .env"
        )

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept-Language": "fr-FR,fr;q=0.9",
        }
    )

    _login(
        session,
        email=settings.discoversnoop_email,
        password=settings.discoversnoop_password,
    )

    params = {
        "export_type": "livepages",
        "format": "csv",
        "country": country,
        "subcountry": "",
        "hours": hours,
        "domain_filter": "",
        "keyword_filter": "",
        "entity_filter": "",
        "social_filter": "",
        "url_filter": "",
        "category_filter": 0,
        "only_new": only_new,
        "preset_filter": 0,
    }
    response = session.get(EXPORT_URL, params=params, timeout=TIMEOUT_S)
    response.raise_for_status()

    # Le fichier est en UTF-8 avec BOM — on demande à requests de
    # décoder en utf-8-sig pour stripper le BOM proprement.
    response.encoding = "utf-8-sig"
    articles = _parse_csv(response.text)

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "country": country,
        "hours_window": hours,
        "only_new": bool(only_new),
        "count": len(articles),
        "articles": articles,
    }


def run() -> dict[str, Any]:
    payload = fetch(
        country=settings.discoversnoop_country,
        hours=settings.discoversnoop_hours,
    )
    write_snapshot(SOURCE_KEY, payload, today_str())
    return payload
