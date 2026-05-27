"""Google News (Actualités) fetcher via RSS public.

Port de gnewsalyzer V2 / google_news.php + cron_google_news.php.

Endpoint : flux RSS publics de news.google.com (français FR).
Aucune auth, gratuit, robuste — c'est l'API de référence du CdC pour
la couverture médiatique.

Format de retour :
  - articles[] avec title, link, source_name, category, published_at
  - Dédupliqués par URL (un article peut apparaître dans plusieurs feeds)

Choix produit : on prend 10 catégories prioritaires (sur les 26 que
gnewsalyzer consomme) pour avoir une bonne couverture sans saturer.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import requests

from server.sources._common import now_iso, today_str, write_snapshot

TIMEOUT_S = 15
SOURCE_KEY = "google_news"

# Sélection pragmatique : feed général + 9 catégories transversales
# couvrant les grandes thématiques (cf cron_google_news.php pour la liste
# complète des 26 IDs si on veut étendre).
FEEDS: dict[str, str] = {
    "general": "https://news.google.com/rss?hl=fr&gl=FR&ceid=FR:fr",
    "france": (
        "https://news.google.com/rss/topics/"
        "CAAqJggKIiBDQkFTRWdvSkwyMHZNR1k0YkRsakVnVm1jaTFHVWlnQVAB"
        "?hl=fr&gl=FR&ceid=FR:fr"
    ),
    "politique": (
        "https://news.google.com/rss/topics/"
        "CAAqIQgKIhtDQkFTRGdvSUwyMHZNRFZ4ZERBU0FtWnlLQUFQAQ"
        "?hl=fr&gl=FR&ceid=FR%3Afr"
    ),
    "international": (
        "https://news.google.com/rss/topics/"
        "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx1YlY4U0JXWnlMVVpTR2dKR1VpZ0FQAQ"
        "?hl=fr&gl=FR&ceid=FR:fr"
    ),
    "economie": (
        "https://news.google.com/rss/topics/"
        "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGx6TVdZU0JXWnlMVVpTR2dKR1VpZ0FQAQ"
        "?hl=fr&gl=FR&ceid=FR:fr"
    ),
    "technologie": (
        "https://news.google.com/rss/topics/"
        "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGRqTVhZU0JXWnlMVVpTR2dKR1VpZ0FQAQ"
        "?hl=fr&gl=FR&ceid=FR:fr"
    ),
    "sports": (
        "https://news.google.com/rss/topics/"
        "CAAqKggKIiRDQkFTRlFvSUwyMHZNRFp1ZEdvU0JXWnlMVVpTR2dKR1VpZ0FQAQ"
        "?hl=fr&gl=FR&ceid=FR:fr"
    ),
    "divertissement": (
        "https://news.google.com/rss/topics/"
        "CAAqKggKIiRDQkFTRlFvSUwyMHZNREpxYW5RU0JXWnlMVVpTR2dKR1VpZ0FQAQ"
        "?hl=fr&gl=FR&ceid=FR:fr"
    ),
    "science": (
        "https://news.google.com/rss/topics/"
        "CAAqKggKIiRDQkFTRlFvSUwyMHZNRFp0Y1RjU0JXWnlMVVpTR2dKR1VpZ0FQAQ"
        "?hl=fr&gl=FR&ceid=FR:fr"
    ),
    "sante": (
        "https://news.google.com/rss/topics/"
        "CAAqJQgKIh9DQkFTRVFvSUwyMHZNR3QwTlRFU0JXWnlMVVpTS0FBUAE"
        "?hl=fr&gl=FR&ceid=FR:fr"
    ),
}

# Titre Google News au format "Article title - Source Name"
# (le tiret est un en dash ou un hyphen selon les feeds)
_TITLE_SOURCE_RE = re.compile(r"\s+[-–—]\s+(?P<source>[^-–—]+)\s*$")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def _split_title_source(raw_title: str, fallback_source: str = "") -> tuple[str, str]:
    """Sépare "Titre - Source" → ("Titre", "Source").

    Si le pattern n'est pas trouvé, retourne le titre brut + fallback_source.
    """
    if not raw_title:
        return "", fallback_source

    match = _TITLE_SOURCE_RE.search(raw_title)
    if not match:
        return raw_title.strip(), fallback_source

    source = match.group("source").strip()
    title = raw_title[: match.start()].strip()
    return title or raw_title.strip(), source or fallback_source


def _parse_feed_xml(xml_text: str, category: str) -> list[dict[str, Any]]:
    """Parse un flux RSS et retourne une liste d'articles normalisés."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items: list[dict[str, Any]] = []
    # RSS 2.0 : <rss><channel><item/></channel></rss>
    for item in root.iter("item"):
        title_raw = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source_name = (source_el.text or "").strip() if source_el is not None else ""
        source_url = source_el.get("url", "") if source_el is not None else ""

        # Le titre Google News inclut souvent " - Source Name" en suffixe
        title, source_from_title = _split_title_source(title_raw, source_name)
        final_source = source_name or source_from_title

        if not title or not link:
            continue

        items.append(
            {
                "title": title,
                "title_raw": title_raw,
                "url": link,
                "source": final_source,
                "source_url": source_url,
                "category": category,
                "published_at": pub_date,
            }
        )

    return items


def _fetch_feed(url: str, category: str) -> list[dict[str, Any]]:
    """Fetch un feed RSS et retourne ses articles parsés."""
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
    response.raise_for_status()
    return _parse_feed_xml(response.text, category=category)


def fetch() -> dict[str, Any]:
    """Récupère tous les feeds, dédup par URL, retourne un payload normalisé.

    En cas d'échec sur un feed, on continue les autres et on log la catégorie
    fautive dans les meta. Un feed cassé ne doit pas tuer toute la source.
    """
    all_articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    failures: list[dict[str, str]] = []
    counts_by_cat: dict[str, int] = {}

    for category, url in FEEDS.items():
        try:
            items = _fetch_feed(url, category)
        except Exception as exc:  # noqa: BLE001
            failures.append({"category": category, "error": f"{type(exc).__name__}: {exc}"})
            counts_by_cat[category] = 0
            continue

        added = 0
        for item in items:
            url_canonical = item["url"]
            if url_canonical in seen_urls:
                continue
            seen_urls.add(url_canonical)
            all_articles.append(item)
            added += 1
        counts_by_cat[category] = added

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "categories": list(FEEDS.keys()),
        "counts_by_category": counts_by_cat,
        "failures": failures,
        "count": len(all_articles),
        "articles": all_articles,
    }


def run() -> dict[str, Any]:
    payload = fetch()
    write_snapshot(SOURCE_KEY, payload, today_str())
    return payload
