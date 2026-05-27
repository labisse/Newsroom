"""Pré-calcul des insights GSC pour le front statique (Vercel).

Génère un JSON enrichi qui combine :
  - Stats globales du projet (total URLs, total clicks, top 20 par clicks)
  - Pour chaque sujet du flux global du jour : score d'affinité avec
    l'historique Discover du site → re-tri par "Project Score"
    (= combinaison du signal global et de l'affinité historique)
  - Pour chaque cluster/catégorie/entité du flux global du jour :
    top-N contenus historiques sémantiquement proches (via RAG)

Le front (project.html) charge ce JSON et affiche le briefing
personnalisé pour le projet, sans avoir besoin de calcul vectoriel
côté browser.

Sortie : data/projects/{slug}/insights.json
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.config import DATA_DIR
from server.scoring import external_sources, title_generator
from server.sources import gsc_rag
from server.sources.gsc_storage import load_history, stats

TOP_K_PER_CLUSTER = 5
TOP_K_PER_SUJET = 10
TOP_URLS_DISPLAYED = 20
# Seuil similarity à partir duquel un article est considéré "pertinent"
# pour le calcul d'affinité (sinon bruit sémantique)
AFFINITY_MIN_SIMILARITY = 0.50
# Seuil clicks minimum pour qu'un match historique soit "intéressant"
# à montrer comme contenu de référence (sinon trop niche pour servir
# d'exemple de réussite éditoriale)
AFFINITY_MIN_CLICKS_FOR_REFERENCE = 5_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_project_name(project_slug: str) -> str:
    """Retourne le nom affichable d'un projet depuis data/projects/index.json.
    Fallback sur le slug capitalisé si introuvable."""
    path = DATA_DIR / "projects" / "index.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for p in payload.get("projects", []):
                if p.get("slug") == project_slug:
                    return p.get("name") or project_slug.title()
        except json.JSONDecodeError:
            pass
    return project_slug.replace("-", " ").title()


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


# ============================================================
# Scoring d'affinité (qualifie un sujet pour un projet donné)
# ============================================================


def compute_affinity(matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Score d'affinité historique pour un sujet donné dans un projet.

    Combine 3 signaux issus du RAG :
      1. Similarité sémantique max (pertinence du meilleur match) : 0-40 pts
      2. Volume de matches pertinents (≥ AFFINITY_MIN_SIMILARITY)   : 0-20 pts
      3. Performance cumulée (total clicks Discover des matches)    : 0-40 pts

    Sémantique :
      - Sujet sans match pertinent → 0 (le site n'a jamais cartonné dessus)
      - Sujet avec 1 match très précis et fort en clicks → ~70
      - Sujet avec 5 matches précis et perf cumulée élevée → ~95-100

    Args:
        matches : sortie de gsc_rag.search_similar (top-K)

    Returns:
        {"score", "match_count", "max_similarity", "avg_similarity",
         "total_clicks", "top_matches"}
    """
    if not matches:
        return {
            "score": 0,
            "match_count": 0,
            "max_similarity": 0.0,
            "avg_similarity": 0.0,
            "total_clicks": 0,
            "top_matches": [],
        }

    # Filtre : on ne garde que les matches au-dessus du seuil de pertinence
    relevant = [m for m in matches if m.get("similarity", 0) >= AFFINITY_MIN_SIMILARITY]

    if not relevant:
        # Aucun match vraiment pertinent → faible signal, mais pas zéro
        # (au moins le RAG a trouvé QQc, ça vaut mieux qu'un sujet
        # complètement nouveau pour le site)
        return {
            "score": 10,
            "match_count": 0,
            "max_similarity": float(matches[0].get("similarity", 0)),
            "avg_similarity": 0.0,
            "total_clicks": 0,
            "top_matches": [],
        }

    max_sim = max(m["similarity"] for m in relevant)
    avg_sim = sum(m["similarity"] for m in relevant) / len(relevant)
    total_clicks = sum(int(m.get("clicks", 0) or 0) for m in relevant)
    count = len(relevant)

    # Composante 1 : similarity max → 0-40 pts (la qualité du meilleur match)
    score_sim = max_sim * 40

    # Composante 2 : nb matches pertinents → 0-20 pts (saturation log)
    # 1 match → 5, 3 matches → 15, 5+ → 20
    score_count = min(20.0, 8.0 * math.log(1 + count))

    # Composante 3 : clicks cumulés → 0-40 pts (saturation log, anchor 100k)
    # 10k → ~5, 100k → ~25, 1M → ~40
    score_clicks = min(40.0, 8.0 * math.log10(1 + total_clicks / 1000.0))

    total_score = round(score_sim + score_count + score_clicks)

    # Top 3 matches pour expand UI :
    # On priorise les matches ≥ 5000 clicks (vrais performers
    # historiques utilisables comme référence éditoriale), puis on
    # complète avec les matches plus faibles si besoin pour avoir 3.
    strong = sorted(
        [m for m in relevant if int(m.get("clicks", 0) or 0) >= AFFINITY_MIN_CLICKS_FOR_REFERENCE],
        key=lambda m: (float(m.get("similarity", 0)), int(m.get("clicks", 0))),
        reverse=True,
    )
    weak = sorted(
        [m for m in relevant if int(m.get("clicks", 0) or 0) < AFFINITY_MIN_CLICKS_FOR_REFERENCE],
        key=lambda m: float(m.get("similarity", 0)),
        reverse=True,
    )
    ranked = strong + weak
    top_matches = [
        {
            "url": m.get("url"),
            "title": m.get("title"),
            "clicks": int(m.get("clicks", 0) or 0),
            "similarity": round(float(m.get("similarity", 0)), 3),
        }
        for m in ranked[:3]
    ]

    return {
        "score": int(min(100, max(0, total_score))),
        "match_count": count,
        "max_similarity": round(float(max_sim), 3),
        "avg_similarity": round(float(avg_sim), 3),
        "total_clicks": total_clicks,
        "top_matches": top_matches,
    }


def compute_project_score(
    global_score: int,
    affinity_score: int,
) -> int:
    """Score composite Sujet × Projet.

    Le sujet doit avoir un signal global (intérêt général) ET être un
    territoire éditorial où le site sait performer. Inversement, un
    sujet à signal global moyen mais où le site cartonne reste pertinent.

    Formule :
      base = 0.55 × global_score + 0.45 × affinity_score
      + bonus +8 si affinity ≥ 70 (sujets historiquement très performants)
      + bonus +4 si global ≥ 70 (sujets ultra-tendance)
    """
    base = 0.55 * global_score + 0.45 * affinity_score
    if affinity_score >= 70:
        base += 8
    if global_score >= 70:
        base += 4
    return int(min(100, max(0, round(base))))


def score_sujets_for_project(
    project_slug: str,
    project_name: str,
    sujets: list[dict[str, Any]],
    *,
    generate_titles: bool = True,
) -> list[dict[str, Any]]:
    """Re-score chaque sujet du flux global pour un projet précis.

    Pour chaque sujet :
      1. Recherche sémantique dans l'historique Discover du projet
      2. Calcul d'affinité (cf compute_affinity)
      3. Project score = combinaison signal global × affinité
      4. Génération d'un titre proposé dans le style du média (Claude)
      5. Récupération de 3 sources externes (GNews + Discover)
      6. Retour de la liste triée par project_score décroissant
    """
    # Reset le cache des sources externes pour utiliser les snapshots
    # les plus récents (gsc-insights peut être appelé après un fetch)
    external_sources.reset_cache()

    scored: list[dict[str, Any]] = []

    for sujet in sujets:
        global_score = int(sujet.get("score", 0))
        query = sujet.get("title", "")
        if not query:
            continue

        # 1-3. RAG search + affinity + project_score
        matches = _enrich_search_results(
            project_slug, query, top_k=TOP_K_PER_SUJET, rerank_by_clicks=False
        )
        affinity = compute_affinity(matches)
        project_score = compute_project_score(global_score, affinity["score"])

        # 4. Titre proposé dans le style du média (best-effort)
        proposed_title: str | None = None
        if generate_titles:
            # On filtre les matches avec un vrai titre (pas un slug brut)
            historical_with_title = [
                m for m in matches if (m.get("title") or "").strip()
            ]
            try:
                proposed_title = title_generator.generate_title(
                    sujet_title=query,
                    project_name=project_name,
                    historical_titles=historical_with_title[:5],
                    sujet_rationale=sujet.get("rationale"),
                )
            except Exception as exc:  # noqa: BLE001
                # Ne plante pas tout le pipeline si Claude échoue
                proposed_title = None
                # Log silencieux — l'absence de titre n'est pas critique
                print(f"  ⚠ title_generator failed for sujet: {exc}")

        # 5. Sources externes (GNews + Discover)
        ext_sources = external_sources.find_external_sources(
            query, top_n=3, include_discover=True
        )

        enriched = {
            "id": sujet.get("id"),
            "title": sujet.get("title"),
            "theme": sujet.get("theme"),
            "global_score": global_score,
            "global_tier": sujet.get("tier"),
            "global_signals": sujet.get("signals", []),
            "rationale": sujet.get("rationale"),
            "msn_url": sujet.get("msn_url"),
            "msn_source_name": sujet.get("msn_source_name"),
            "discover_category": sujet.get("discover_category"),
            "discover_entities": sujet.get("discover_entities"),
            "affinity": affinity,
            "project_score": project_score,
            "proposed_title": proposed_title,
            "external_sources": ext_sources,
        }
        scored.append(enriched)

    # Tri par project_score décroissant + rank final
    scored.sort(key=lambda s: s["project_score"], reverse=True)
    for i, s in enumerate(scored, start=1):
        s["project_rank"] = i
    return scored


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

    # 2. Charger le flux global (sujets + catégories + clusters + entités)
    sujets_payload = _load_global_sujets()
    sujets = (sujets_payload or {}).get("sujets") or []
    cats_trending = (sujets_payload or {}).get("categories_trending") or []
    entity_clusters = (sujets_payload or {}).get("entity_clusters") or []
    entities_trending = (sujets_payload or {}).get("entities_trending") or []

    # 2bis. RE-SCORER les sujets du flux global pour ce projet
    # (= le vrai briefing personnalisé)
    project_name = _resolve_project_name(project_slug)
    scored_sujets = (
        score_sujets_for_project(project_slug, project_name, sujets)
        if sujets
        else []
    )

    # Distribution par tier du Project Score (utile pour les compteurs hero)
    project_tier_counts = {"high": 0, "medium": 0, "low": 0}
    for s in scored_sujets:
        ps = s["project_score"]
        if ps >= 50:
            project_tier_counts["high"] += 1
        elif ps >= 30:
            project_tier_counts["medium"] += 1
        else:
            project_tier_counts["low"] += 1

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
            "sujets_count": len(sujets),
            "categories_count": len(cats_trending),
            "entity_clusters_count": len(entity_clusters),
            "entities_count": len(entities_trending),
        },
        # ★ Le briefing personnalisé du projet (objet principal pour le front)
        "scored_sujets": scored_sujets,
        "project_tier_counts": project_tier_counts,
        # Insights par dimension (sections secondaires)
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
