"""Pré-calcul des insights GSC pour le front statique (Vercel).

Génère un JSON enrichi qui combine :
  - Stats globales du projet (total URLs, total clicks, top 20 par clicks)
  - Pour chaque cluster/catégorie/entité du flux global du jour :
    top-N contenus historiques sémantiquement proches (via RAG)

Le front (project.html) charge ce JSON et affiche tout sans avoir
besoin de calcul vectoriel côté browser. Permet de garder Vercel
100% statique tout en exposant le RAG à l'utilisateur.

Sortie : data/projects/{slug}/insights.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.config import DATA_DIR
from server.sources import gsc_rag
from server.sources.gsc_storage import load_history, stats

TOP_K_PER_CLUSTER = 5
TOP_URLS_DISPLAYED = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_global_sujets() -> dict[str, Any] | None:
    """Charge data/sujets/latest.json (sortie du scoring global).

    Retourne None si le fichier n'existe pas (cas où on a pas encore
    lancé `score`).
    """
    path = DATA_DIR / "sujets" / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _top_urls_for_stats(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retourne les top URLs formatées pour la section stats."""
    sorted_items = sorted(
        items, key=lambda x: x.get("clicks_total", 0), reverse=True
    )
    return [
        {
            "url": item.get("url", ""),
            "title": item.get("title") or None,
            "clicks": int(item.get("clicks_total", 0)),
            "impressions": int(item.get("impressions_total", 0)),
        }
        for item in sorted_items[:TOP_URLS_DISPLAYED]
    ]


def _enrich_search_results(
    project_slug: str,
    query: str,
    *,
    top_k: int = TOP_K_PER_CLUSTER,
    rerank_by_clicks: bool = True,
) -> list[dict[str, Any]]:
    """Wrap autour de search_similar avec un format adapté au front.

    Retourne une liste vide en cas d'erreur (ex. index pas encore généré),
    pour ne pas planter le pré-calcul de tout le fichier.
    """
    try:
        return gsc_rag.search_similar(
            project_slug,
            query,
            top_k=top_k,
            rerank_by_clicks=rerank_by_clicks,
        )
    except Exception:  # noqa: BLE001
        return []


def build_insights(project_slug: str) -> dict[str, Any]:
    """Pipeline complet : stats + RAG cross-search → JSON unique."""
    # 1. Stats globales du projet
    items = load_history(project_slug)
    if not items:
        raise RuntimeError(
            f"Aucune URL en base pour '{project_slug}'. "
            f"Lance d'abord gsc-fetch."
        )
    project_stats = stats(project_slug)
    top_urls = _top_urls_for_stats(items)

    # 2. Charger le flux global (catégories + clusters + entités du jour)
    sujets_payload = _load_global_sujets()
    cats_trending = (sujets_payload or {}).get("categories_trending") or []
    entity_clusters = (sujets_payload or {}).get("entity_clusters") or []
    entities_trending = (sujets_payload or {}).get("entities_trending") or []

    # 3. Pour chaque cat/cluster/entité, faire une recherche RAG
    by_category: list[dict[str, Any]] = []
    for cat in cats_trending:
        query = cat.get("label") or cat.get("key") or ""
        matches = _enrich_search_results(project_slug, query)
        by_category.append(
            {
                "key": cat.get("key"),
                "label": cat.get("label"),
                "global_articles_count": cat.get("articles_count"),
                "global_total_score": cat.get("total_score"),
                "query": query,
                "matches": matches,
            }
        )

    by_entity_cluster: list[dict[str, Any]] = []
    for cluster in entity_clusters:
        members = cluster.get("members") or []
        # Query = label + members joints (le label est déjà le premier
        # member dans cluster_entities_by_cooccurrence)
        query = " ".join(members) if members else cluster.get("label", "")
        matches = _enrich_search_results(project_slug, query)
        by_entity_cluster.append(
            {
                "label": cluster.get("label"),
                "members": members,
                "global_articles_count": cluster.get("articles_count"),
                "global_total_score": cluster.get("total_score"),
                "query": query,
                "matches": matches,
            }
        )

    by_entity: list[dict[str, Any]] = []
    # On limite aux 10 entités plates les plus performantes pour
    # ne pas exploser la taille du JSON
    for ent in entities_trending[:10]:
        query = ent.get("name", "")
        matches = _enrich_search_results(project_slug, query)
        by_entity.append(
            {
                "name": ent.get("name"),
                "global_articles_count": ent.get("articles_count"),
                "global_total_score": ent.get("total_score"),
                "query": query,
                "matches": matches,
            }
        )

    payload = {
        "project": project_slug,
        "generated_at": _now_iso(),
        "stats": {
            "total_urls": project_stats["total_urls"],
            "with_title": project_stats["with_title"],
            "without_title": project_stats["without_title"],
            "total_clicks": project_stats["total_clicks"],
            "top_urls": top_urls,
        },
        "sujets_source": {
            "available": sujets_payload is not None,
            "generated_at": (sujets_payload or {}).get("generated_at"),
            "categories_count": len(cats_trending),
            "entity_clusters_count": len(entity_clusters),
            "entities_count": len(entities_trending),
        },
        "insights": {
            "by_category": by_category,
            "by_entity_cluster": by_entity_cluster,
            "by_entity": by_entity,
        },
    }
    return payload


def insights_path(project_slug: str) -> Path:
    return DATA_DIR / "projects" / project_slug / "insights.json"


def write_insights(project_slug: str, payload: dict[str, Any]) -> Path:
    path = insights_path(project_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def run(project_slug: str) -> dict[str, Any]:
    """Pipeline complet + sauvegarde."""
    payload = build_insights(project_slug)
    write_insights(project_slug, payload)
    return payload
