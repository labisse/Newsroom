"""TikTok via RapidAPI (tiktok-api23.p.rapidapi.com).

TikTok ne propose pas l'API Research officielle pour usage commercial
(reserve aux academiques / not-for-profit basees UE+Bresil). On passe
donc par un proxy RapidAPI qui scrape l'app publique TikTok.

Strategie pour cibler FR :
  L'endpoint /api/post/trending est global (Tagalog/anglais dominent).
  L'endpoint /api/search/general?keyword=X retourne des vrais resultats
  FR si X est un mot-cle FR (france, actu, politique...).

On fait donc N petites searches FR au lieu d'1 trending global.
Couts RapidAPI : 1 req/search * N searches * 4 runs/jour. Pour N=5,
on est a 600 req/mois (compatible plans freemium).

Format retourne aligne sur les autres sources : count + items[] avec
title (= desc TikTok), url, stats (vues, likes, comments, shares),
author, hashtags, created_at, velocity (vues/h).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import requests

from server.config import settings
from server.sources._common import now_iso, today_str, write_snapshot

TIMEOUT_S = 25
SOURCE_KEY = "tiktok"
RAPIDAPI_HOST = "tiktok-api23.p.rapidapi.com"
SEARCH_URL = f"https://{RAPIDAPI_HOST}/api/search/general"

# Mots-cles FR qui rapportent du signal editorial (testes manuellement).
# A ajuster apres quelques jours d'usage : retirer ceux qui ramenent du
# bruit, ajouter ceux qui rapportent du news quality (chaines, hashtags).
SEARCH_KEYWORDS: list[str] = [
    "france",
    "actu",
    "politique",
    "info",
    "macron",
]

# Limite par search (RapidAPI plafonne souvent autour de 12-30 par page)
ITEMS_PER_SEARCH = 20

# Filtre temporel : on ne garde que les videos publiees dans les
# 7 derniers jours, sinon on pollue avec du vieux viral.
MAX_AGE_HOURS = 24 * 7


def _hours_since(timestamp: int | str | None) -> float:
    """createTime TikTok est un epoch (secondes). Retourne age en heures."""
    if not timestamp:
        return 0.0
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return 0.0
    age_s = (datetime.now(timezone.utc) - datetime.fromtimestamp(ts, timezone.utc)).total_seconds()
    return max(0.0, age_s / 3600.0)


def _extract_hashtags(desc: str) -> list[str]:
    """Extrait les #hashtags d'une description. Lowercased, dedup."""
    if not desc:
        return []
    tags = re.findall(r"#([\wÀ-ÿ]+)", desc.lower())
    return list(dict.fromkeys(tags))[:8]  # dedup en preservant l'ordre


def _build_item(raw: dict[str, Any], search_keyword: str) -> dict[str, Any] | None:
    """Transforme un item TikTok brut en format normalise."""
    vid_id = raw.get("id")
    if not vid_id:
        return None

    desc = (raw.get("desc") or "").strip()
    author = raw.get("author") or {}
    if isinstance(author, dict):
        author_name = author.get("uniqueId") or author.get("nickname") or ""
    else:
        author_name = str(author)
    stats = raw.get("stats") or raw.get("statsV2") or {}

    create_time = raw.get("createTime")
    age_h = _hours_since(create_time)
    if age_h > MAX_AGE_HOURS:
        return None
    if age_h <= 0:
        age_h = 1.0  # evite division par 0 dans velocity

    play_count = int(stats.get("playCount") or 0)
    velocity = int(play_count / age_h) if age_h > 0.5 else play_count

    return {
        "id": str(vid_id),
        # Titre : desc TikTok (souvent emoji + hashtags). Pas top mais
        # c'est tout ce qu'on a pour le matching downstream.
        "title": desc[:200] or f"TikTok by @{author_name}",
        "url": f"https://www.tiktok.com/@{author_name}/video/{vid_id}" if author_name else "",
        "description": desc[:500],
        "author": author_name,
        "author_nickname": author.get("nickname", "") if isinstance(author, dict) else "",
        "hashtags": _extract_hashtags(desc),
        "search_keyword": search_keyword,
        "created_at": (
            datetime.fromtimestamp(int(create_time), timezone.utc).isoformat()
            if create_time
            else ""
        ),
        "hours_old": round(age_h, 1),
        "views": play_count,
        "likes": int(stats.get("diggCount") or 0),
        "comments": int(stats.get("commentCount") or 0),
        "shares": int(stats.get("shareCount") or 0),
        "collects": int(stats.get("collectCount") or 0),
        "velocity_views_per_hour": velocity,
    }


def _search(keyword: str, api_key: str) -> tuple[list[dict[str, Any]], str | None]:
    """Lance une search keyword. Retourne (items, error_msg_or_None)."""
    params = {"keyword": keyword, "cursor": "0", "search_id": "0"}
    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": api_key,
    }
    try:
        r = requests.get(SEARCH_URL, params=params, headers=headers, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        return [], f"network_error: {type(exc).__name__}"

    if r.status_code == 429:
        return [], "rate_limit_429"
    if r.status_code == 403:
        return [], "forbidden_403_check_quota_or_key"
    if r.status_code >= 400:
        return [], f"http_{r.status_code}: {r.text[:120]}"

    try:
        payload = r.json()
    except ValueError:
        return [], "invalid_json_response"

    raw_items = payload.get("item_list") or []
    return raw_items[:ITEMS_PER_SEARCH], None


def fetch(api_key: str | None = None) -> dict[str, Any]:
    """Fetch trending FR TikTok via multi-search RapidAPI."""
    key = api_key or settings.rapidapi_tiktok_key

    if not key:
        return {
            "source": SOURCE_KEY,
            "fetched_at": now_iso(),
            "count": 0,
            "items": [],
            "searches": [],
            "failures": [{
                "reason": "missing_api_key",
                "hint": "Set RAPIDAPI_TIKTOK_KEY in .env (RapidAPI dashboard)",
            }],
        }

    by_id: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    per_search: list[dict[str, Any]] = []

    for kw in SEARCH_KEYWORDS:
        raw_items, err = _search(kw, key)
        per_search.append({
            "keyword": kw,
            "fetched": len(raw_items),
            "error": err,
        })
        if err:
            failures.append({"keyword": kw, "reason": err})
            continue
        for raw in raw_items:
            item = _build_item(raw, search_keyword=kw)
            if item is None:
                continue
            # Dedup par id : si une video matche plusieurs keywords, on
            # garde la 1ere occurrence (mais on note les keywords supplements)
            if item["id"] in by_id:
                existing = by_id[item["id"]]
                if kw not in existing.get("matched_keywords", []):
                    existing.setdefault("matched_keywords", [existing["search_keyword"]]).append(kw)
            else:
                item["matched_keywords"] = [kw]
                by_id[item["id"]] = item

    items = list(by_id.values())
    # Tri par velocity (= vues/h) decroissant : ce qui monte vite
    items.sort(key=lambda v: v["velocity_views_per_hour"], reverse=True)

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "count": len(items),
        "per_search": per_search,
        "items": items,
        "failures": failures,
    }


def run() -> dict[str, Any]:
    payload = fetch()
    write_snapshot(SOURCE_KEY, payload, today_str())
    return payload
