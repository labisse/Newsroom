"""Recuperation des sources externes traitant un sujet donne.

Pour un sujet, on cherche les articles de presse qui le couvrent dans
les sources externes deja collectees :
  - Google News (data/google_news/latest.json) : prioritaire — medias
    francais de reference (Le Monde, BFM, France Info, etc.)
  - Discoversnoop (data/discoversnoop/latest.json) : optionnel, complete
    avec des articles "a fort potentiel Discover"

Le matching utilise les **embeddings Voyage** (cosine similarity) plutot
que Jaccard token-based. Raisons :
  - Jaccard avec fallback permissif (2 tokens communs) ramenait des
    faux positifs ridicules : un sujet "cancer 15 ans" matchait
    "Dell Wall Street" sur 2 numeros communs.
  - Embeddings semantiques captent le SUJET, pas les mots. Cancer/
    sante/medecin sont proches, finance/bourse loin.

Seuil cosine 0.72 (calibre conservateur) : si aucun article ne
match, on retourne [] plutot que de polluer le briefing avec du HS.

Si Voyage indisponible (cle absente, timeout), on degrade en
mode Jaccard strict (pas de fallback permissif) pour ne jamais
retourner de bruit, quitte a retourner vide.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from server.config import DATA_DIR
from server.scoring import embeddings
from server.scoring.matcher import jaccard
from server.scoring.normalize import token_set

# Seuil cosine pour considerer qu'un article externe traite le meme
# sujet. Calibre avec voyage-3 multilingue, plus strict que le seuil
# de semantic_dedup (0.78) car ici on veut zero bruit.
COSINE_THRESHOLD = 0.72

# Fallback Jaccard si Voyage indisponible. Strict uniquement (pas de
# pass permissif) : mieux vaut 0 source que des faux positifs.
JACCARD_FALLBACK_THRESHOLD = 0.35
JACCARD_MIN_COMMON = 3

# Cache process-local pour ne pas reparser les JSON a chaque sujet
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
    """A appeler au debut d'un run pour forcer le rechargement des JSON."""
    global _gnews_cache, _discover_cache
    _gnews_cache = None
    _discover_cache = None


def _match_semantic(
    sujet_title: str,
    candidates: list[dict[str, Any]],
    *,
    title_key: str,
) -> list[tuple[float, dict[str, Any]]]:
    """Match semantique via Voyage embeddings.

    Retourne [(cosine_sim, candidate), ...] tries par similarite
    decroissante, filtres au seuil COSINE_THRESHOLD.
    """
    titles = [(c.get(title_key) or "").strip() for c in candidates]
    valid = [(i, t) for i, t in enumerate(titles) if t]
    if not valid:
        return []

    texts_to_embed = [sujet_title] + [t for _, t in valid]

    try:
        vectors, _ = embeddings.embed_batch(texts_to_embed)
    except Exception:  # noqa: BLE001
        # Propage pour que l'appelant degrade en Jaccard
        raise

    matrix = np.asarray(vectors, dtype=np.float32)
    # Remplace les inf/nan eventuels (vecteurs corrompus en cache) par 0
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    # Floor a 1.0 pour les vecteurs nuls (apres division leur cosine sera 0)
    norms = np.where(norms < 1e-9, 1.0, norms)
    matrix_n = matrix / norms

    query_vec = matrix_n[0]
    cand_vecs = matrix_n[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        sims = cand_vecs @ query_vec  # cosine car deja normalises
    sims = np.nan_to_num(sims, nan=0.0, posinf=0.0, neginf=0.0)

    matched: list[tuple[float, dict[str, Any]]] = []
    for (orig_idx, _), sim in zip(valid, sims):
        s = float(sim)
        if s >= COSINE_THRESHOLD:
            matched.append((s, candidates[orig_idx]))

    matched.sort(key=lambda x: x[0], reverse=True)
    return matched


def _match_jaccard_strict(
    sujet_title: str,
    candidates: list[dict[str, Any]],
    *,
    title_key: str,
) -> list[tuple[float, dict[str, Any]]]:
    """Fallback Jaccard strict si Voyage est indisponible."""
    src_tokens = token_set(sujet_title)
    if not src_tokens:
        return []

    matched: list[tuple[float, dict[str, Any]]] = []
    for cand in candidates:
        title = cand.get(title_key) or ""
        cand_tokens = token_set(title)
        if not cand_tokens:
            continue
        common = src_tokens & cand_tokens
        score = jaccard(src_tokens, cand_tokens)
        if score >= JACCARD_FALLBACK_THRESHOLD and len(common) >= JACCARD_MIN_COMMON:
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
    """Consomme des matches scores et les ajoute a out jusqu'a max_total."""
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
        out.append({
            "source": source_label,
            "title": title,
            "url": url,
            "publisher": cand.get(publisher_key) or "",
            "published_at": cand.get(date_key) or "",
            "similarity": round(float(score), 3),
        })


def find_external_sources(
    sujet_title: str,
    *,
    top_n: int = 3,
    include_discover: bool = True,
) -> list[dict[str, Any]]:
    """Pour un sujet, retourne top N articles externes qui le couvrent.

    Strategie :
      1. Pass semantique Voyage (cosine >= 0.72) sur GNews puis Discover
      2. Si Voyage indisponible : fallback Jaccard strict (>= 0.35 + 3 tokens)
      3. Pas de "pass permissif" : mieux vaut 0 source que des HS

    Le seuil 0.72 est conservateur, calibre pour eviter les faux positifs
    qui polluaient le briefing (ex: cancer + Dell, cancer + Iran).
    """
    if not sujet_title:
        return []

    gnews = _load_gnews()
    discover = _load_discover() if include_discover else []

    # Decide backend : semantique si voyage dispo, sinon jaccard strict
    match_fn = _match_semantic
    backend_label = "voyage"

    out: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    try:
        gnews_scored = _match_semantic(
            sujet_title, gnews, title_key="title"
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"[external_sources] Voyage KO ({type(exc).__name__}: {exc}) — "
            "fallback Jaccard strict"
        )
        match_fn = _match_jaccard_strict
        backend_label = "jaccard"
        gnews_scored = match_fn(sujet_title, gnews, title_key="title")

    _consume_matches(
        gnews_scored,
        source_label="gnews",
        publisher_key="source",
        date_key="published_at",
        out=out,
        seen_urls=seen_urls,
        seen_titles=seen_titles,
        max_total=top_n,
    )

    if include_discover and len(out) < top_n:
        try:
            discover_scored = match_fn(
                sujet_title, discover, title_key="title"
            )
        except Exception:  # noqa: BLE001
            discover_scored = _match_jaccard_strict(
                sujet_title, discover, title_key="title"
            )
        _consume_matches(
            discover_scored,
            source_label="discover",
            publisher_key="publisher",
            date_key="firstviewed",
            out=out,
            seen_urls=seen_urls,
            seen_titles=seen_titles,
            max_total=top_n,
        )

    # Tri final par similarite decroissante (deja fait par chaque source
    # mais on re-trie globalement pour avoir le top global)
    out.sort(key=lambda x: x["similarity"], reverse=True)
    return out[:top_n]
