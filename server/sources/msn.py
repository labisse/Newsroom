"""MSN News fetcher.

Port de gnewsalyzer V2 / cron_msn_news.php. L'endpoint
assets.msn.com/service/news/feed retourne un JSON où les articles
sont soit directement dans `value[]`, soit imbriqués dans
`value[].subCards[]`.

Pas d'auth réelle : la clé apikey est publique et embarquée dans
l'URL (la même que celle utilisée par msn.com côté navigateur).
"""

from __future__ import annotations

from typing import Any

import requests

from server.config import settings
from server.sources._common import (
    now_iso,
    sha256,
    today_str,
    write_snapshot,
)

ENDPOINT = "https://assets.msn.com/service/news/feed"
TIMEOUT_S = 30
SOURCE_KEY = "msn"


def _extract_article(item: dict[str, Any]) -> dict[str, Any] | None:
    """Normalise un item brut MSN en dict article propre.

    Reprend exactement la logique de extractArticleData() côté PHP.
    """
    if not item.get("title") or not item.get("url"):
        return None

    # Votes
    upvotes = 0
    downvotes = 0
    sub_reactions = (
        item.get("reactionSummary", {})
        .get("subReactionSummaries", {})
        .get("$values", [])
    )
    if isinstance(sub_reactions, list):
        for reaction in sub_reactions:
            r_type = str(reaction.get("type", "")).lower()
            count = int(reaction.get("totalCount", 0) or 0)
            if r_type == "upvote":
                upvotes = count
            elif r_type == "downvote":
                downvotes = count

    # Image
    image_url: str | None = None
    images = item.get("images")
    if isinstance(images, list) and images and isinstance(images[0], dict):
        image_url = images[0].get("url")
    elif isinstance(item.get("image"), dict):
        image_url = item["image"].get("url")

    # Catégorie
    category = (
        item.get("category") or item.get("categoryKey") or item.get("vertical") or ""
    )
    category = str(category).strip().lower()

    # Topics
    topics: list[str] = []
    raw_topics = item.get("topics")
    if isinstance(raw_topics, list):
        for topic in raw_topics:
            if isinstance(topic, str):
                if topic:
                    topics.append(topic)
            elif isinstance(topic, dict):
                name = topic.get("label") or topic.get("name") or ""
                if name:
                    topics.append(name)

    # Commentaires
    comments = int((item.get("commentSummary") or {}).get("totalCount", 0) or 0)

    url = item["url"]
    return {
        "msn_id": item.get("id", ""),
        "url": url,
        "url_hash": sha256(url),
        "title": item["title"],
        "abstract": item.get("abstract", ""),
        "image_url": image_url,
        "source": (item.get("provider") or {}).get("name", "MSN"),
        "category": category,
        "topics": topics,
        "published_at": item.get("publishedDateTime"),
        "upvotes": upvotes,
        "downvotes": downvotes,
        "comments": comments,
    }


def _walk_feed(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parcourt la réponse MSN et en extrait tous les articles."""
    articles: list[dict[str, Any]] = []
    for feed_item in data.get("value", []) or []:
        if not isinstance(feed_item, dict):
            continue

        # Articles ou vidéos directs
        if feed_item.get("type") in {"article", "video"}:
            article = _extract_article(feed_item)
            if article:
                articles.append(article)

        # subCards imbriqués
        for sub in feed_item.get("subCards") or []:
            if not isinstance(sub, dict):
                continue
            if sub.get("type") in {"article", "video"}:
                article = _extract_article(sub)
                if article:
                    articles.append(article)

    return articles


def fetch() -> dict[str, Any]:
    """Récupère le feed MSN et retourne un payload normalisé."""
    if not settings.msn_api_key:
        raise RuntimeError("MSN_API_KEY manquant dans .env")

    params = {
        "apikey": settings.msn_api_key,
        "market": settings.msn_market,
        "$top": settings.msn_limit,
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "fr-FR,fr;q=0.9",
    }

    response = requests.get(
        ENDPOINT,
        params=params,
        headers=headers,
        timeout=TIMEOUT_S,
    )
    response.raise_for_status()
    data = response.json()

    articles = _walk_feed(data)

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "market": settings.msn_market,
        "count": len(articles),
        "articles": articles,
    }


def run() -> dict[str, Any]:
    """Fetch + write snapshot. Retourne le payload."""
    payload = fetch()
    write_snapshot(SOURCE_KEY, payload, today_str())
    return payload
