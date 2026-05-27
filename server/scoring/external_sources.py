"""Récupération des sources externes traitant un sujet donné.

Pour un sujet, on cherche les articles de presse qui le couvrent dans
les sources externes déjà collectées :
  - Google News (data/google_news/latest.json) : prioritaire — médias
    français de référence (Le Monde, BFM, France Info, etc.)
  - Discoversnoop (data/discoversnoop/latest.json) : optionnel, complète
    avec des articles "à fort potentiel Discover"

Le matching réutilise le Jaccard sur tokens normalisés (cf
server/scoring/matcher.py), mais avec un seuil plus strict pour ne
garder que les articles vraiment liés.
"""

from __future__ import annotations

import json
from typing import Any

from server.config import DATA_DIR
from server.scoring.matcher import jaccard
from server.scoring.normalize import token_set

# Cache process-local pour ne pas reparser les JSON à chaque sujet
_gnews_cache: list[dict[str, Any]] | None = None
_discover_cache: list[dict[str, Any]] | None = None


def _load_gnews() -> list[dict[str, Any]]:
    global _gnews_cache
    if _gnews_cache is not None:
        return _gnews_cache
    path = DATA_DIR / "google_news" / "latest.json"
    if not path.exists():
        _gnews_cache = []
        return _gnews_cache
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        _gnews_cache = payload.get("articles") or []
    except json.JSONDecodeError:
        _gnews_cache = []
    return _gnews_cache


def _load_discover() -> list[dict[str, Any]]:
    global _discover_cache
    if _discover_cache is not None:
        return _discover_cache
    path = DATA_DIR / "discoversnoop" / "latest.json"
    if not path.exists():
        _discover_cache = []
        return _discover_cache
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        _discover_cache = payload.get("articles") or []
    except json.JSONDecodeError:
        _discover_cache = []
    return _discover_cache


def reset_cache() -> None:
    """À appeler au début d'un run pour forcer le rechargement des JSON."""
    global _gnews_cache, _discover_cache
    _gnews_cache = None
    _discover_cache = None


def _score_candidates(
    src_tokens: set[str],
    candidates: list[dict[str, Any]],
    *,
    title_key: str,
    min_common: int = 3,
    jaccard_threshold: float = 0.30,
) -> list[tuple[float, dict[str, Any]]]:
    """Filtre + score les candidats. Retourne [(jaccard_score, candidate), ...]."""
    matched: list[tuple[float, dict[str, Any]]] = []
    for cand in candidates:
        title = cand.get(title_key) or ""
        cand_tokens = token_set(title)
        if not cand_tokens:
            continue
        common = src_tokens & cand_tokens
        score = jaccard(src_tokens, cand_tokens)
        if score >= jaccard_threshold or len(common) >= min_common:
            matched.append((score, cand))
    matched.sort(key=lambda x: x[0], reverse=True)
    return matched


def _consume_matches(
    candidates_scored: list[tuple[float, dict[str, Any]]],
    *,
    source_label: str,
    publisher_key: str,
    date_key: str,
    out: list[dict[str, Any]],
    seen_urls: set[str],
    seen_titles: set[str],
    max_total: int,
) -> None:
    """Consomme des matches scorés et les ajoute à `out` jusqu'à max_total."""
    for score, cand in candidates_scored:
        if len(out) >= max_total:
            return
        url = cand.get("url", "")
        title = (cand.get("title") or "").strip()
        if not url or url in seen_urls:
            continue
        if title.lower() in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title.lower())
        out.append(
            {
                "source": source_label,
                "title": title,
                "url": url,
                "publisher": cand.get(publisher_key) or "",
                "published_at": cand.get(date_key) or "",
                "similarity": round(float(score), 3),
            }
        )


def find_external_sources(
    sujet_title: str,
    *,
    top_n: int = 3,
    include_discover: bool = True,
) -> list[dict[str, Any]]:
    """Pour un sujet, retourne top N articles externes qui le couvrent.

    Stratégie en 2 passes (strict → permissif) pour ne JAMAIS retourner
    vide quand un signal existe :
      1. Pass strict : GNews + Discover avec min_common=3, jaccard ≥ 0.30
      2. Pass permissif (fallback) : min_common=2, jaccard ≥ 0.20
    Tri final par similarité décroissante.
    """
    if not sujet_title:
        return []

    src_tokens = token_set(sujet_title)
    if not src_tokens:
        return []

    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[dict[str, Any]] = []

    gnews = _load_gnews()
    discover = _load_discover() if include_discover else []

    # ── Pass 1 : seuils stricts (qualité prioritaire) ──
    gnews_strict = _score_candidates(
        src_tokens, gnews, title_key="title", min_common=3, jaccard_threshold=0.30
    )
    _consume_matches(
        gnews_strict,
        source_label="gnews",
        publisher_key="source",
        date_key="published_at",
        out=out,
        seen_urls=seen_urls,
        seen_titles=seen_titles,
        max_total=top_n,
    )

    if include_discover and len(out) < top_n:
        discover_strict = _score_candidates(
            src_tokens, discover, title_key="title",
            min_common=3, jaccard_threshold=0.30,
        )
        _consume_matches(
            discover_strict,
            source_label="discover",
            publisher_key="publisher",
            date_key="firstviewed",
            out=out,
            seen_urls=seen_urls,
            seen_titles=seen_titles,
            max_total=top_n,
        )

    # ── Pass 2 : fallback plus permissif si pas assez ──
    if len(out) < top_n:
        gnews_loose = _score_candidates(
            src_tokens, gnews, title_key="title",
            min_common=2, jaccard_threshold=0.20,
        )
        _consume_matches(
            gnews_loose,
            source_label="gnews",
            publisher_key="source",
            date_key="published_at",
            out=out,
            seen_urls=seen_urls,
            seen_titles=seen_titles,
            max_total=top_n,
        )

    if include_discover and len(out) < top_n:
        discover_loose = _score_candidates(
            src_tokens, discover, title_key="title",
            min_common=2, jaccard_threshold=0.20,
        )
        _consume_matches(
            discover_loose,
            source_label="discover",
            publisher_key="publisher",
            date_key="firstviewed",
            out=out,
            seen_urls=seen_urls,
            seen_titles=seen_titles,
            max_total=top_n,
        )

    # Tri final par similarité (les pass strict gardent leur priorité
    # grâce à un score Jaccard plus élevé en moyenne)
    out.sort(key=lambda x: x["similarity"], reverse=True)
    return out[:top_n]
