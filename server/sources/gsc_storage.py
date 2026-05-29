"""Stockage append-only des URLs Discover par projet.

Format JSONL — une ligne par URL :
{
  "url": "https://parismatch.com/...",
  "url_hash": "sha256...",
  "title": "Titre éditorial nettoyé",  # null si pas encore scrapé
  "title_raw": "Titre brut <title>",   # null si pas encore scrapé
  "title_scraped_at": "2026-05-27T...", # null si pas encore scrapé
  "clicks_total": 12450,
  "impressions_total": 198000,
  "first_seen_at": "2026-04-15T...",
  "last_seen_at": "2026-05-27T...",
  "sync_count": 3
}

Choix JSONL :
  - append-friendly, mais on réécrit le fichier complet sur upsert
    pour rester cohérent (volume max attendu : quelques milliers
    d'URLs sur 12 mois, file < 5 Mo)
  - dédup par url_hash (sha256 de l'URL canonique)
  - update incrémental des métriques (on garde MAX(clicks_total)
    + MAX(impressions_total) entre runs successifs)

Pour gros volumes (>50k URLs/projet), migrer vers SQLite (cf TODO).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from server.config import DATA_DIR


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def history_path(project_slug: str) -> Path:
    """data/projects/{slug}/discover_history.jsonl"""
    p = DATA_DIR / "projects" / project_slug / "discover_history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_history(project_slug: str) -> list[dict[str, Any]]:
    """Lit tout l'historique en mémoire (dict-list)."""
    path = history_path(project_slug)
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                # Ligne corrompue — on saute et on log côté caller
                continue
    return items


def save_history(project_slug: str, items: Iterable[dict[str, Any]]) -> int:
    """Écrit (overwrite) tout l'historique. Retourne le nb de lignes écrites."""
    path = history_path(project_slug)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False))
            f.write("\n")
            count += 1
    return count


def upsert_discover_rows(
    project_slug: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Merge des rows GSC (au format fetch_search_analytics) dans l'historique.

    Stratégie :
      - URL connue → update last_seen_at + sync_count, clicks/impressions
        prennent le MAX entre la valeur historisée et la nouvelle
        (GSC retourne du cumulatif par défaut sur la période demandée)
      - URL inconnue → insert avec first_seen_at = now
      - Titre conservé tel quel s'il existe déjà (le scraping est un
        pas séparé, cf scrape_titles)

    Args:
        rows: liste de {url, clicks, impressions, ctr}

    Returns:
        {"inserted": int, "updated": int, "total": int}
    """
    existing = {item["url_hash"]: item for item in load_history(project_slug)}
    now = _now()
    inserted = 0
    updated = 0

    for row in rows:
        url = (row.get("url") or "").strip()
        if not url:
            continue

        url_hash = _url_hash(url)
        new_clicks = int(row.get("clicks", 0) or 0)
        new_impressions = int(row.get("impressions", 0) or 0)

        if url_hash in existing:
            item = existing[url_hash]
            item["clicks_total"] = max(
                int(item.get("clicks_total", 0)), new_clicks
            )
            item["impressions_total"] = max(
                int(item.get("impressions_total", 0)), new_impressions
            )
            item["last_seen_at"] = now
            item["sync_count"] = int(item.get("sync_count", 0)) + 1
            updated += 1
        else:
            existing[url_hash] = {
                "url": url,
                "url_hash": url_hash,
                "title": None,
                "title_raw": None,
                "title_scraped_at": None,
                "clicks_total": new_clicks,
                "impressions_total": new_impressions,
                "first_seen_at": now,
                "last_seen_at": now,
                "sync_count": 1,
            }
            inserted += 1

    # Tri par clicks décroissants pour lisibilité du JSONL
    items_sorted = sorted(
        existing.values(),
        key=lambda x: x.get("clicks_total", 0),
        reverse=True,
    )
    save_history(project_slug, items_sorted)

    return {
        "inserted": inserted,
        "updated": updated,
        "total": len(items_sorted),
    }


def items_missing_title(
    project_slug: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Retourne les URLs sans titre scrapé (ou avec titre vide).

    Tri par clicks_total décroissant : avec un limit faible (ex: 2000), on
    scrape d'abord les URLs à fort trafic — c'est là que l'amélioration
    sémantique RAG aura le plus d'impact pour le briefing éditorial.
    """
    out = [
        item
        for item in load_history(project_slug)
        if not item.get("title")
    ]
    out.sort(key=lambda i: int(i.get("clicks_total") or 0), reverse=True)
    if limit:
        return out[:limit]
    return out


def update_title(
    project_slug: str,
    url_hash: str,
    *,
    title: str | None,
    title_raw: str | None,
) -> bool:
    """Met à jour le titre d'une URL existante. Retourne True si trouvée."""
    items = load_history(project_slug)
    found = False
    for item in items:
        if item.get("url_hash") == url_hash:
            item["title"] = title
            item["title_raw"] = title_raw
            item["title_scraped_at"] = _now()
            found = True
            break
    if found:
        save_history(project_slug, items)
    return found


def stats(project_slug: str) -> dict[str, Any]:
    """Statistiques rapides sur l'historique d'un projet."""
    items = load_history(project_slug)
    if not items:
        return {
            "total_urls": 0,
            "with_title": 0,
            "without_title": 0,
            "total_clicks": 0,
            "top_url": None,
        }
    with_title = sum(1 for x in items if x.get("title"))
    total_clicks = sum(int(x.get("clicks_total", 0)) for x in items)
    top = max(items, key=lambda x: int(x.get("clicks_total", 0)))
    return {
        "total_urls": len(items),
        "with_title": with_title,
        "without_title": len(items) - with_title,
        "total_clicks": total_clicks,
        "top_url": {
            "url": top["url"],
            "title": top.get("title"),
            "clicks": int(top.get("clicks_total", 0)),
        },
    }
