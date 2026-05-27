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


def find_external_sources(
    sujet_title: str,
    *,
    top_n: int = 3,
    include_discover: bool = True,
) -> list[dict[str, Any]]:
    """Pour un sujet, retourne top N articles externes qui le couvrent.

    Stratégie :
      1. Match Google News (médias de référence) — prioritaire
      2. Si pas assez de matches, complète avec Discoversnoop
      3. Dédup par URL et par titre

    Returns:
        Liste de dicts {source, title, url, similarity, publisher,
        published_at} triée par similarité.
    """
    if not sujet_title:
        return []

    src_tokens = token_set(sujet_title)
    if not src_tokens:
        return []

    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[dict[str, Any]] = []

    # 1. Google News
    gnews = _load_gnews()
    gnews_matches = _score_candidates(
        src_tokens, gnews, title_key="title", min_common=3, jaccard_threshold=0.30
    )
    for score, cand in gnews_matches:
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
                "source": "gnews",
                "title": title,
                "url": url,
                "publisher": cand.get("source") or "",
                "published_at": cand.get("published_at") or "",
                "similarity": round(float(score), 3),
            }
        )
        if len(out) >= top_n:
            return out

    # 2. Discoversnoop en complément si pas assez
    if include_discover and len(out) < top_n:
        discover = _load_discover()
        discover_matches = _score_candidates(
            src_tokens,
            discover,
            title_key="title",
            min_common=3,
            jaccard_threshold=0.30,
        )
        for score, cand in discover_matches:
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
                    "source": "discover",
                    "title": title,
                    "url": url,
                    "publisher": cand.get("publisher") or "",
                    "published_at": cand.get("firstviewed") or "",
                    "similarity": round(float(score), 3),
                }
            )
            if len(out) >= top_n:
                return out

    return out
