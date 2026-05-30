"""YouTube Trending FR : top vidéos populaires via YouTube Data API v3.

Endpoint :
  https://www.googleapis.com/youtube/v3/videos
    ?part=snippet,statistics
    &chart=mostPopular
    &regionCode=FR
    &maxResults=50
    &key=YOUR_KEY

Coût : 1 unité de quota par appel (10 000 unités/jour gratuit → on peut
appeler 10k fois par jour). On fait 1 appel par run.

Pourquoi YouTube anticipe Discover :
  Une vidéo qui explose en vues/h (BFM, Brut, Konbini, chaînes news)
  reflète un sujet qui va sortir sur Discover dans les heures qui
  suivent. C'est particulièrement vrai pour people / sport / faits
  divers / politique.

Format de retour :
  - videos[] avec id, title, channel, channel_id, views, likes, comments,
    duration, published_at, thumbnail, category_id, tags
  - On filtre les vidéos < 1h pour éviter le bruit (replays anciens
    qui restent en trending), gardé seulement si extrêmement populaire.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from server.config import settings
from server.sources._common import now_iso, today_str, write_snapshot

TIMEOUT_S = 15
SOURCE_KEY = "youtube_trending"
MAX_RESULTS = 50  # cap API = 50 par page

# Catégories YouTube intéressantes pour le signal éditorial.
# (Si on veut filtrer plus tard, sinon on prend tout.)
INTERESTING_CATEGORY_IDS = {
    "1": "Films & animation",
    "10": "Musique",
    "17": "Sport",
    "20": "Jeux vidéo",
    "22": "Vlogs",
    "23": "Comédie",
    "24": "Divertissement",
    "25": "Actualités & politique",
    "26": "Conseils & style",
    "27": "Éducation",
    "28": "Sciences & tech",
}


def _parse_iso8601_duration(duration: str) -> int:
    """PT4M13S → 253 (secondes). PT1H2M30S → 3750."""
    if not duration:
        return 0
    pattern = re.compile(
        r"PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?"
    )
    match = pattern.match(duration)
    if not match:
        return 0
    h = int(match.group("h") or 0)
    m = int(match.group("m") or 0)
    s = int(match.group("s") or 0)
    return h * 3600 + m * 60 + s


def _hours_since(iso_ts: str) -> float:
    """Combien d'heures depuis published_at."""
    if not iso_ts:
        return 0.0
    try:
        # YouTube renvoie ISO 8601 avec Z final
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    delta = datetime.now(timezone.utc) - dt
    return delta.total_seconds() / 3600.0


def fetch(api_key: str | None = None, region: str | None = None) -> dict[str, Any]:
    """Récupère les vidéos en trending FR. Retourne un payload structuré.

    Si la clé API n'est pas configurée, retourne un payload vide avec
    `failures` rempli — le pipeline continue mais ne bénéficie pas du
    signal YouTube.
    """
    key = api_key or settings.youtube_api_key
    reg = (region or settings.youtube_region or "FR").upper()

    if not key:
        return {
            "source": SOURCE_KEY,
            "fetched_at": now_iso(),
            "region": reg,
            "count": 0,
            "videos": [],
            "failures": [
                {
                    "reason": "missing_api_key",
                    "hint": "Set YOUTUBE_API_KEY in .env (Google Cloud Console)",
                }
            ],
        }

    params = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": reg,
        "maxResults": MAX_RESULTS,
        "key": key,
    }

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params=params,
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {
            "source": SOURCE_KEY,
            "fetched_at": now_iso(),
            "region": reg,
            "count": 0,
            "videos": [],
            "failures": [
                {"reason": "api_error", "error": f"{type(exc).__name__}: {exc}"}
            ],
        }

    items = payload.get("items", [])
    videos: list[dict[str, Any]] = []
    for item in items:
        snippet = item.get("snippet") or {}
        stats = item.get("statistics") or {}
        content = item.get("contentDetails") or {}

        title = (snippet.get("title") or "").strip()
        if not title:
            continue
        video_id = item.get("id") or ""
        thumbs = snippet.get("thumbnails") or {}
        # Prend la meilleure thumbnail dispo (high → medium → default)
        thumb_url = ""
        for size in ("maxres", "high", "medium", "default"):
            tb = thumbs.get(size)
            if tb and tb.get("url"):
                thumb_url = tb["url"]
                break

        duration_s = _parse_iso8601_duration(content.get("duration") or "")
        published_at = snippet.get("publishedAt") or ""
        hours_old = _hours_since(published_at)

        views = int(stats.get("viewCount") or 0)
        # Velocity = vues / heure depuis publication (proxy de "ça monte")
        velocity = views / hours_old if hours_old > 0.5 else views

        videos.append(
            {
                "id": video_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
                "channel": snippet.get("channelTitle") or "",
                "channel_id": snippet.get("channelId") or "",
                "description": (snippet.get("description") or "")[:300],
                "category_id": snippet.get("categoryId") or "",
                "category_label": INTERESTING_CATEGORY_IDS.get(
                    snippet.get("categoryId") or "", "Autre"
                ),
                "tags": snippet.get("tags") or [],
                "published_at": published_at,
                "hours_old": round(hours_old, 1),
                "views": views,
                "likes": int(stats.get("likeCount") or 0),
                "comments": int(stats.get("commentCount") or 0),
                "duration_s": duration_s,
                "velocity_views_per_hour": int(velocity),
                "thumbnail": thumb_url,
            }
        )

    # Tri par velocity décroissante (= ce qui monte le plus vite,
    # meilleur prédicteur Discover que vues totales brutes)
    videos.sort(key=lambda v: v["velocity_views_per_hour"], reverse=True)

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "region": reg,
        "count": len(videos),
        "videos": videos,
        "failures": [],
    }


def run() -> dict[str, Any]:
    payload = fetch()
    write_snapshot(SOURCE_KEY, payload, today_str())
    return payload
