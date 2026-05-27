"""Scraper de titre d'article + nettoyage du suffixe site.

GSC retourne uniquement URL + clicks + impressions. Pour avoir le
titre éditorial (utile au RAG et à l'UX), on scrape la balise
<title> de chaque URL, puis on retire le pattern courant
" - NomDuSite" / " | NomDuSite" / " :: NomDuSite".

Politesse :
  - timeout court (10s)
  - User-Agent identifiable
  - 1 req max parallèle (pas d'async pour le POC, append séquentiel)
  - retry-once sur 429 / 5xx avec backoff
  - log les échecs mais ne plante pas le pipeline

Pour le scraping HTML on reste sur regex stdlib pour éviter la
dépendance bs4 — le pattern <title>...</title> est assez stable.
"""

from __future__ import annotations

import html
import re
import time
from typing import Iterable
from urllib.parse import urlparse

import requests

from server.sources.gsc_storage import (
    items_missing_title,
    update_title,
)

# ── Configuration ──
TIMEOUT_S = 10
USER_AGENT = (
    "EditorialSignalBot/0.1 (+https://github.com/labisse/Newsroom) "
    "Mozilla/5.0 (compatible; Editorial Signal title fetcher)"
)
SLEEP_BETWEEN_REQS_S = 0.5  # politesse : ~2 req/s max
MAX_RETRIES = 1

# ── Regex ──
_TITLE_RE = re.compile(
    r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL
)
# Séparateurs courants entre titre et nom de site
_SEPARATORS = (" - ", " | ", " :: ", " — ", " – ", " · ", " • ", " : ")


def _clean_title_raw(raw: str) -> str:
    """Décode entités HTML + normalise whitespace."""
    if not raw:
        return ""
    text = html.unescape(raw)
    # Retirer balises résiduelles (au cas où)
    text = re.sub(r"<[^>]+>", "", text)
    # Normaliser whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _site_name_candidates(url: str) -> list[str]:
    """Génère les noms de site probables pour un URL.

    Pour parismatch.com on génère : ["Paris Match", "ParisMatch",
    "Parismatch", "Paris-Match", "parismatch", "parismatch.com"].
    Le titre peut être suffixé par n'importe lequel de ces formats.
    """
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if not host:
        return []
    bare = host.split(".")[0]  # parismatch

    out = {host, bare}

    # CamelCase intelligent : couper sur les frontières de "mot"
    # parismatch → ["paris", "match"] → "Paris Match", "ParisMatch", "Paris-Match"
    # futurasciences → ["futura", "sciences"] (heuristique simple par dictionnaire)
    parts = _split_compound(bare)
    if len(parts) > 1:
        joined_space = " ".join(p.capitalize() for p in parts)
        joined_pascal = "".join(p.capitalize() for p in parts)
        joined_dash = "-".join(p.capitalize() for p in parts)
        out.update([joined_space, joined_pascal, joined_dash])

    # Capitalize simple
    out.add(bare.capitalize())

    return sorted(out, key=len, reverse=True)  # le plus long d'abord


# Petit dictionnaire de mots fréquents en noms de sites FR
_KNOWN_WORDS = {
    "paris", "match", "futura", "sciences", "le", "la", "les", "monde",
    "figaro", "parisien", "ouest", "france", "info", "tv", "mag",
    "magazine", "presse", "actu", "actualite", "news", "journal",
    "media", "today", "express", "obs", "point", "huffington", "post",
}


def _split_compound(word: str) -> list[str]:
    """Tente de séparer un mot composé via le petit dico (heuristique simple)."""
    if len(word) <= 4:
        return [word]
    for i in range(3, len(word) - 2):
        left, right = word[:i], word[i:]
        if left in _KNOWN_WORDS and right in _KNOWN_WORDS:
            return [left, right]
    # Pas de match — on retourne le mot complet
    return [word]


def strip_site_suffix(raw_title: str, url: str) -> str:
    """Retire le suffixe " - NomDuSite" du titre s'il y est."""
    if not raw_title:
        return ""

    candidates = _site_name_candidates(url)
    if not candidates:
        return raw_title

    text = raw_title
    # Essayer chaque séparateur + chaque candidat
    for sep in _SEPARATORS:
        for cand in candidates:
            suffix = f"{sep}{cand}"
            if text.lower().endswith(suffix.lower()):
                return text[: -len(suffix)].rstrip()
    return text


def _fetch_html(url: str) -> str | None:
    """Récupère le HTML d'une URL. None en cas d'échec."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }
    attempts = 0
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            response = requests.get(
                url, headers=headers, timeout=TIMEOUT_S, allow_redirects=True
            )
        except requests.RequestException:
            return None
        if response.status_code == 200:
            return response.text
        if response.status_code in (429, 500, 502, 503, 504) and attempts <= MAX_RETRIES:
            time.sleep(2)
            continue
        return None
    return None


def extract_title_from_html(html_text: str, url: str) -> tuple[str | None, str | None]:
    """Parse la balise <title> et retire le suffixe site.

    Returns:
        (title_propre, title_raw)
    """
    if not html_text:
        return None, None
    match = _TITLE_RE.search(html_text)
    if not match:
        return None, None
    raw = _clean_title_raw(match.group(1))
    if not raw:
        return None, None
    clean = strip_site_suffix(raw, url)
    return clean, raw


def fetch_title(url: str) -> tuple[str | None, str | None]:
    """Scrape un titre depuis une URL. Returns (clean, raw)."""
    html_text = _fetch_html(url)
    if not html_text:
        return None, None
    return extract_title_from_html(html_text, url)


def scrape_missing_titles(
    project_slug: str,
    *,
    limit: int | None = None,
    on_progress=None,
) -> dict[str, int]:
    """Scrape les titres des URLs qui n'en ont pas encore.

    Args:
        project_slug : projet cible
        limit        : nb max d'URLs à scraper (None = toutes)
        on_progress  : callback(done, total, url) pour log live

    Returns:
        {"scraped": int, "skipped": int, "failed": int, "remaining": int}
    """
    pending = items_missing_title(project_slug, limit=limit)
    total = len(pending)
    scraped = 0
    failed = 0

    for idx, item in enumerate(pending):
        url = item["url"]
        url_hash = item["url_hash"]
        if on_progress:
            on_progress(idx + 1, total, url)

        clean, raw = fetch_title(url)
        if clean is None:
            failed += 1
        else:
            scraped += 1
        # On enregistre même les échecs (avec null) pour ne pas re-tenter
        # à chaque run — sauf si on veut explicitement réessayer
        update_title(project_slug, url_hash, title=clean, title_raw=raw)

        # Politesse entre requêtes
        if idx < total - 1:
            time.sleep(SLEEP_BETWEEN_REQS_S)

    remaining = max(0, len(items_missing_title(project_slug)))
    return {
        "scraped": scraped,
        "failed": failed,
        "total_processed": total,
        "remaining": remaining,
    }
