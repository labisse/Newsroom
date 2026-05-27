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
# Pour les projets avec `strict_topical_filter`, un sujet sans alignement
# thématique peut tout de même rester s'il a une affinité sémantique très
# forte (≥ ce seuil) — protection contre les faux négatifs.
HIGH_AFFINITY_OVERRIDE_SIMILARITY = 0.78

# Expansion de mots-clés thématiques pour la détection d'alignement.
# Volontairement minimal (les thèmes Futura et PM aujourd'hui), à étendre
# au fur et à mesure des nouveaux projets.
THEME_KEYWORD_EXPANSIONS: dict[str, list[str]] = {
    "sciences": [
        "science", "scientifique", "scientifiques", "recherche", "découverte",
        "découvertes", "étude", "laboratoire", "physique", "chimie", "biologie",
        "mathématique", "expérience",
    ],
    "tech": [
        "tech", "technologie", "technologique", "ia", "intelligence artificielle",
        "robot", "robotique", "numérique", "informatique", "ordinateur",
        "chatgpt", "openai", "google", "apple", "microsoft", "cyberattaque",
        "cybersécurité", "smartphone", "android", "iphone", "internet",
    ],
    "espace": [
        "espace", "spatial", "astronomie", "astronome", "cosmos", "nasa",
        "spacex", "esa", "planète", "planètes", "galaxie", "étoile", "trou noir",
        "lune", "mars", "fusée", "satellite", "univers", "exoplanète",
    ],
    "santé": [
        "santé", "médical", "médicament", "médecine", "maladie", "cancer",
        "virus", "vaccin", "épidémie", "alzheimer", "obésité", "diabète",
        "covid", "hôpital", "patient", "psychiatrie", "neurologie",
    ],
    "environnement": [
        "environnement", "climat", "climatique", "réchauffement", "écologie",
        "écologique", "biodiversité", "pollution", "carbone", "co2", "énergie",
        "renouvelable", "espèce", "espèces", "forêt", "océan", "canicule",
        "sécheresse", "inondation", "ouragan", "cyclone",
    ],
    "people": [
        "acteur", "actrice", "chanteur", "chanteuse", "star", "célébrité",
        "festival", "cannes", "interview", "couple", "divorce", "mariage",
    ],
    "royauté": [
        "roi", "reine", "prince", "princesse", "royal", "royale", "monarchie",
        "windsor", "buckingham", "monaco", "monégasque",
    ],
    "politique": [
        "politique", "élu", "député", "président", "ministre", "élection",
        "gouvernement", "assemblée", "parti", "sénat", "macron", "mélenchon",
        "le pen",
    ],
    "société": [
        "société", "social", "sociale", "violence", "féminicide",
        "discrimination", "manifestation",
    ],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_project_config(project_slug: str) -> dict[str, Any]:
    """Charge la config d'un projet depuis data/projects/index.json.
    Retourne {} si introuvable."""
    path = DATA_DIR / "projects" / "index.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    for p in payload.get("projects", []):
        if p.get("slug") == project_slug:
            return p
    return {}


def _resolve_project_name(project_slug: str) -> str:
    """Retourne le nom affichable d'un projet depuis data/projects/index.json."""
    cfg = _load_project_config(project_slug)
    return cfg.get("name") or project_slug.replace("-", " ").title()


def _normalize_title_for_dedup(title: str) -> str:
    """Hash léger pour dédupliquer les sujets : minuscules + suppression
    ponctuation + 60 premiers caractères. Suffit pour repérer les doublons
    quasi-identiques entre MSN/Discover/GNews."""
    import re

    cleaned = re.sub(r"[^\w\s]", " ", title.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:60]


def _theme_keywords_for_project(project_cfg: dict[str, Any]) -> set[str]:
    """Retourne l'ensemble des mots-clés thématiques attendus pour ce projet
    (themes + expansions). Utilisé pour le matching GNews."""
    themes = [t.lower().strip() for t in (project_cfg.get("themes") or [])]
    keywords: set[str] = set()
    for theme in themes:
        for kw in THEME_KEYWORD_EXPANSIONS.get(theme, [theme]):
            keywords.add(kw)
    return keywords


def _title_matches_themes(title: str, keywords: set[str]) -> str | None:
    """Retourne le premier mot-clé thématique trouvé dans le titre, ou None.
    Match mot-entier pour éviter les faux positifs (tech ≠ discothèque)."""
    haystack = f" {title.lower()} "
    for kw in keywords:
        if f" {kw} " in haystack:
            return kw
    return None


def _category_matches(article_category: str, project_categories: list[str]) -> str | None:
    """Vérifie si la catégorie d'un article Discover chevauche celles du projet.
    Retourne la catégorie projet qui matche, ou None."""
    if not article_category:
        return None
    art_lc = article_category.lower().strip()
    for pcat in project_categories or []:
        pcat_lc = pcat.lower().strip()
        if not pcat_lc:
            continue
        if art_lc.startswith(pcat_lc) or pcat_lc.startswith(art_lc):
            return pcat
    return None


def _discover_to_candidate(article: dict[str, Any], matched_cat: str) -> dict[str, Any]:
    """Convertit un article Discover en sujet candidat compatible avec le
    pipeline de scoring projet. Le 'score' Discover (0-65) est mappé vers un
    global_score 0-60 pour rester comparable aux sujets MSN-sourcés."""
    raw_score = float(article.get("score") or 0)
    # Discover : 0.5 → 30, 5 → 60, 30+ → 95. Saturation log.
    if raw_score <= 0:
        global_score = 15
    else:
        global_score = int(min(95, 30 + 20 * math.log10(1 + raw_score)))

    if raw_score >= 10:
        value = f"{raw_score:.0f}/65"
    elif raw_score >= 1:
        value = f"{raw_score:.1f}/65"
    else:
        value = "présent"

    signals = [
        {"source": "gsc", "label": "discover", "value": value},
    ]
    publisher = article.get("publisher") or "Discover"
    entities = list(article.get("entities_list") or [])

    return {
        "id": f"d_{abs(hash(article.get('url', ''))) % 10**8}",
        "title": article.get("title", ""),
        "theme": (matched_cat.split("/")[-1] if matched_cat else "actualité"),
        "score": global_score,
        "tier": "high" if global_score >= 60 else "medium",
        "rationale": (
            f"Repéré dans Google Discover ({publisher}) "
            f"sur le territoire éditorial du projet ({matched_cat})."
        ),
        "signals": signals,
        "msn_url": article.get("url"),
        "msn_source_name": publisher,
        "discover_category": article.get("category"),
        "discover_entities": entities,
        "source_origin": "discover",
    }


def _gnews_to_candidate(article: dict[str, Any], matched_kw: str) -> dict[str, Any]:
    """Convertit un article GNews en sujet candidat. Le global_score est
    modeste car GNews seul = juste de la couverture média, pas de signal
    d'engagement."""
    publisher = article.get("source") or "Google News"
    return {
        "id": f"g_{abs(hash(article.get('url', ''))) % 10**8}",
        "title": article.get("title", ""),
        "theme": "actualité",
        "score": 25,  # Base modeste, à booster par l'affinité GSC
        "tier": "medium",
        "rationale": (
            f"Repéré dans Google Actualités ({publisher}) "
            f"sur un mot-clé du territoire éditorial ({matched_kw})."
        ),
        "signals": [
            {"source": "news", "label": "gnews", "value": publisher},
        ],
        "msn_url": article.get("url"),
        "msn_source_name": publisher,
        "discover_category": None,
        "discover_entities": [],
        "source_origin": "gnews",
    }


MAX_DISCOVER_CANDIDATES = 40
MAX_GNEWS_CANDIDATES = 30


def _gather_project_candidates(
    project_cfg: dict[str, Any],
    existing_titles: set[str],
) -> list[dict[str, Any]]:
    """Élargit le pool de candidats avec les articles Discover + GNews qui
    touchent directement le territoire éditorial du projet.

    Pour les projets spécialisés (cf strict_topical_filter), MSN seul ne
    suffit pas : ses 100 articles couvrent surtout people/politique. On va
    chercher les 1000+ articles Discover et 400+ GNews qui matchent les
    catégories/thèmes du projet.

    Dédup par titre normalisé contre `existing_titles` (sujets MSN déjà
    scorés) ET entre candidats Discover/GNews eux-mêmes.
    """
    candidates: list[dict[str, Any]] = []
    seen = set(existing_titles)

    # --- Discover : filtre par catégorie ---
    discover_path = DATA_DIR / "discoversnoop" / "latest.json"
    if discover_path.exists():
        try:
            payload = json.loads(discover_path.read_text(encoding="utf-8"))
            articles = payload.get("articles") or []
        except json.JSONDecodeError:
            articles = []
        # Tri par score Discover décroissant pour prioriser les top potentiels
        articles_sorted = sorted(
            articles, key=lambda a: float(a.get("score") or 0), reverse=True
        )
        discover_added = 0
        for art in articles_sorted:
            if discover_added >= MAX_DISCOVER_CANDIDATES:
                break
            title = art.get("title") or ""
            if not title:
                continue
            matched_cat = _category_matches(
                art.get("category") or "", project_cfg.get("categories") or []
            )
            if not matched_cat:
                continue
            key = _normalize_title_for_dedup(title)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_discover_to_candidate(art, matched_cat))
            discover_added += 1

    # --- GNews : filtre par mot-clé thématique ---
    gnews_path = DATA_DIR / "google_news" / "latest.json"
    if gnews_path.exists():
        try:
            payload = json.loads(gnews_path.read_text(encoding="utf-8"))
            articles = payload.get("articles") or []
        except json.JSONDecodeError:
            articles = []
        keywords = _theme_keywords_for_project(project_cfg)
        gnews_added = 0
        for art in articles:
            if gnews_added >= MAX_GNEWS_CANDIDATES:
                break
            title = art.get("title") or ""
            if not title:
                continue
            matched_kw = _title_matches_themes(title, keywords)
            if not matched_kw:
                continue
            key = _normalize_title_for_dedup(title)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_gnews_to_candidate(art, matched_kw))
            gnews_added += 1

    return candidates


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


def compute_affinity(
    matches: list[dict[str, Any]],
    *,
    min_similarity: float = AFFINITY_MIN_SIMILARITY,
) -> dict[str, Any]:
    """Score d'affinité historique pour un sujet donné dans un projet.

    Combine 3 signaux issus du RAG :
      1. Similarité sémantique max (pertinence du meilleur match) : 0-40 pts
      2. Volume de matches pertinents (≥ min_similarity)            : 0-20 pts
      3. Performance cumulée (total clicks Discover des matches)    : 0-40 pts

    Args:
        matches        : sortie de gsc_rag.search_similar (top-K)
        min_similarity : seuil minimal pour qu'un match soit considéré pertinent.
                         À calibrer par projet (cf affinity_min_similarity dans
                         data/projects/index.json) : généralistes type PM ~0.50,
                         spécialisés type Futura ~0.65.
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
    relevant = [m for m in matches if m.get("similarity", 0) >= min_similarity]

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


def thematic_alignment(
    sujet: dict[str, Any],
    project_cfg: dict[str, Any],
) -> tuple[bool, str]:
    """Vérifie si un sujet s'inscrit dans le territoire éditorial du projet.

    Deux signaux combinés (OU logique) :
      1. La `discover_category` du sujet est un préfixe de l'une des
         catégories Discover du projet (ex: '/Science/Astronomy' chevauche
         '/Science').
      2. Au moins un mot-clé thématique (project.themes + expansions) est
         présent dans le titre ou les entités du sujet.

    Retourne (matched: bool, reason: str). La raison sert au debug et peut
    être affichée côté front pour expliquer pourquoi un sujet est gardé.
    """
    # 1. Match par préfixe de catégorie Discover
    sujet_cat = (sujet.get("discover_category") or "").lower().strip()
    if sujet_cat:
        for pcat in project_cfg.get("categories") or []:
            pcat_lc = pcat.lower().strip()
            if not pcat_lc:
                continue
            if sujet_cat.startswith(pcat_lc) or pcat_lc.startswith(sujet_cat):
                return True, f"category:{pcat}"

    # 2. Match par mots-clés thématiques (titre + entités)
    title_lc = (sujet.get("title") or "").lower()
    entities = sujet.get("discover_entities") or []
    entities_lc = " ".join(str(e) for e in entities).lower()
    haystack = f"{title_lc} {entities_lc}"

    themes = [t.lower().strip() for t in (project_cfg.get("themes") or [])]
    for theme in themes:
        keywords = THEME_KEYWORD_EXPANSIONS.get(theme, [theme])
        for kw in keywords:
            # Match mot-entier pour éviter "tech" → "discothèque"
            kw_padded = f" {kw} "
            haystack_padded = f" {haystack} "
            if kw_padded in haystack_padded:
                return True, f"theme:{theme}({kw})"

    return False, ""


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
    project_cfg: dict[str, Any] | None = None,
    generate_titles: bool = True,
    affinity_min_similarity: float = AFFINITY_MIN_SIMILARITY,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Re-score chaque sujet du flux global pour un projet précis.

    Pour chaque sujet :
      1. Recherche sémantique dans l'historique Discover du projet
      2. Calcul d'affinité (cf compute_affinity)
      3. Filtre topical optionnel si project.strict_topical_filter == true
         (sites spécialisés type Futura : on exclut les sujets sans
         alignement thématique avec project.categories / project.themes,
         sauf si l'affinité sémantique est extrêmement forte)
      4. Project score = combinaison signal global × affinité
      5. Génération d'un titre proposé dans le style du média (Claude)
      6. Récupération de 3 sources externes (GNews + Discover)
      7. Retour de la liste triée par project_score décroissant

    Retourne (sujets_kept, filter_meta). filter_meta contient :
      - total_candidates : nombre de sujets globaux examinés
      - kept              : nombre retenus
      - excluded_off_topic: nombre filtrés faute d'alignement thématique
      - strict_topical    : True/False (mode activé pour ce projet)
    """
    # Reset le cache des sources externes pour utiliser les snapshots
    # les plus récents (gsc-insights peut être appelé après un fetch)
    external_sources.reset_cache()

    cfg = project_cfg or {}
    strict = bool(cfg.get("strict_topical_filter", False))

    scored: list[dict[str, Any]] = []
    excluded_off_topic = 0

    for sujet in sujets:
        global_score = int(sujet.get("score", 0))
        query = sujet.get("title", "")
        if not query:
            continue

        # 1-3. RAG search + affinity
        matches = _enrich_search_results(
            project_slug, query, top_k=TOP_K_PER_SUJET, rerank_by_clicks=False
        )
        affinity = compute_affinity(matches, min_similarity=affinity_min_similarity)

        # Filtre topical strict pour projets spécialisés
        topical_match = False
        topical_reason = ""
        if strict:
            topical_match, topical_reason = thematic_alignment(sujet, cfg)
            # Override : on garde quand même si l'affinité sémantique est très
            # forte (un sujet peut être thématiquement off mais sémantiquement
            # très proche d'un contenu phare du site)
            high_aff_override = (
                affinity["max_similarity"] >= HIGH_AFFINITY_OVERRIDE_SIMILARITY
                and affinity["match_count"] >= 3
            )
            if not (topical_match or high_aff_override):
                excluded_off_topic += 1
                continue

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
            "topical_match": topical_match if strict else None,
            "topical_reason": topical_reason if strict else None,
            # Origine du candidat (msn par défaut, discover/gnews pour les
            # candidats injectés par _gather_project_candidates)
            "source_origin": sujet.get("source_origin", "msn"),
        }
        scored.append(enriched)

    # Tri par project_score décroissant + rank final
    scored.sort(key=lambda s: s["project_score"], reverse=True)
    for i, s in enumerate(scored, start=1):
        s["project_rank"] = i

    filter_meta = {
        "total_candidates": len(sujets),
        "kept": len(scored),
        "excluded_off_topic": excluded_off_topic,
        "strict_topical": strict,
    }
    return scored, filter_meta


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
    project_cfg = _load_project_config(project_slug)
    project_name = (
        project_cfg.get("name") or project_slug.replace("-", " ").title()
    )
    # Seuil d'affinité calibré par projet (généralistes ~0.50,
    # spécialisés ~0.65) : évite les faux positifs sémantiques sur les
    # sites à territoire éditorial restreint (cf Futura Sciences).
    affinity_threshold = float(
        project_cfg.get("affinity_min_similarity", AFFINITY_MIN_SIMILARITY)
    )

    # Pour les projets spécialisés : élargir le pool de candidats avec les
    # articles Discover (par catégorie) et GNews (par mot-clé thématique)
    # touchant directement le territoire éditorial. MSN seul ne suffit pas
    # (100 articles généralistes), on a 1000+ Discover et 400+ GNews dont
    # une partie est dans le territoire du projet.
    candidates = list(sujets)
    extra_candidates_meta = {"discover": 0, "gnews": 0}
    if project_cfg.get("strict_topical_filter"):
        existing_titles = {
            _normalize_title_for_dedup(s.get("title", "")) for s in sujets
        }
        extra = _gather_project_candidates(project_cfg, existing_titles)
        for c in extra:
            if c.get("source_origin") == "discover":
                extra_candidates_meta["discover"] += 1
            elif c.get("source_origin") == "gnews":
                extra_candidates_meta["gnews"] += 1
        candidates.extend(extra)

    if candidates:
        scored_sujets, filter_meta = score_sujets_for_project(
            project_slug,
            project_name,
            candidates,
            project_cfg=project_cfg,
            affinity_min_similarity=affinity_threshold,
        )
    else:
        scored_sujets = []
        filter_meta = {
            "total_candidates": 0,
            "kept": 0,
            "excluded_off_topic": 0,
            "strict_topical": bool(project_cfg.get("strict_topical_filter", False)),
        }
    filter_meta["extra_candidates"] = extra_candidates_meta

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
        # Métadonnées du filtre topical (utile pour expliciter côté UI
        # combien de sujets globaux ont été écartés car hors-territoire)
        "topical_filter": filter_meta,
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
