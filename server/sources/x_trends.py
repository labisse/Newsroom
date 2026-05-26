"""X (Twitter) Trends via scraping trends24.in.

Port de gnewsalyzer V2 / cron_twitter_trends.php.

trends24.in expose la liste des tendances X/Twitter France en HTML.
La regex matche les blocs:
  <span class=trend-name><a ...>QUERY</a><span class=tweet-count ...>COUNT</span></span>

Le `tweet-count` peut être vide (cas fréquent depuis la fin de l'API
Twitter publique côté trends24) — on retombe alors sur 0.

Fragile aux changements DOM mais 0 € pour le POC, conformément
au choix consigné dans le CdC (X API Basic = 100 €/mois reportée).
"""

from __future__ import annotations

import re
from typing import Any

import requests

from server.config import settings
from server.sources._common import (
    now_iso,
    today_hour_str,
    write_snapshot,
)

TIMEOUT_S = 20
SOURCE_KEY = "x_trends"

# Regex (équivalent du preg_match_all PHP, en plus tolérante)
TREND_RE = re.compile(
    r'<span class=trend-name>'
    r'<a[^>]*>(?P<query>.*?)</a>'
    r'<span class=tweet-count[^>]*>(?P<count>.*?)</span>'
    r'</span>',
    re.DOTALL,
)

TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return TAG_RE.sub("", text).strip()


def _parse_count(raw: str) -> int:
    """Convertit "12.4K tweets" / "1.2M" / "" → int."""
    if not raw:
        return 0
    cleaned = _strip_tags(raw).strip()
    if not cleaned:
        return 0
    # Garder uniquement le premier token "1.2K", "500", "1M"
    token = cleaned.split()[0]
    multiplier = 1
    if token.endswith("K"):
        token = token[:-1]
        multiplier = 1_000
    elif token.endswith("M"):
        token = token[:-1]
        multiplier = 1_000_000
    try:
        return int(float(token) * multiplier)
    except ValueError:
        return 0


def fetch(url: str | None = None) -> dict[str, Any]:
    """Récupère et parse la page trends24.in/france/."""
    url = url or settings.x_trends_url
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }

    response = requests.get(url, headers=headers, timeout=TIMEOUT_S)
    response.raise_for_status()
    html = response.text

    trends: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in TREND_RE.finditer(html):
        query = _strip_tags(match.group("query"))
        if not query or query in seen:
            continue
        seen.add(query)
        trends.append(
            {
                "query": query,
                "tweet_count": _parse_count(match.group("count")),
            }
        )

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "region": "france",
        "url": url,
        "count": len(trends),
        "trends": trends,
    }


def run() -> dict[str, Any]:
    payload = fetch()
    # Source horaire — snapshot horodaté pour pouvoir tracer la vélocité.
    write_snapshot(SOURCE_KEY, payload, today_hour_str())
    return payload
