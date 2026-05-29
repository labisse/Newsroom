"""RAG sémantique sur l'historique Discover d'un projet.

Pipeline :
  1. Pour chaque URL en base (data/projects/{slug}/discover_history.jsonl) :
     extraire le texte à embedder (title si dispo, sinon slug nettoyé)
  2. Calculer le vecteur via embeddings.embed_batch (Voyage ou TF-IDF)
  3. Stocker l'index dans data/projects/{slug}/embeddings.npz :
     - vectors  : matrix (N, D) float32
     - urls     : array N strings
     - titles   : array N strings (peut être vide)
     - clicks   : array N int (utile pour ré-ranking)
     - backend  : str ("voyage" ou "tfidf")
     - dim      : int

  4. search_similar(project_slug, query, top_k) → top-K URLs proches
     sémantiquement, avec leur similarité + clicks Discover historiques.

Le RAG est rebuild from scratch à chaque appel `gsc-embed` — c'est rapide
(<2 min pour 12k URLs en TF-IDF, ~30s en Voyage avec cache chaud) et
ça évite la complexité d'un index incrémental.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np

from server.config import DATA_DIR
from server.scoring import embeddings
from server.sources.gsc_storage import load_history

# ──────────────────────────────────────────────────────────────
# Extraction du texte à embedder
# ──────────────────────────────────────────────────────────────

_SLUG_TAIL_NUM_RE = re.compile(r"-?\d{4,}$")  # ID numérique de fin (-266276)


def slug_to_text(url: str) -> str:
    """Extrait un texte humain depuis l'URL si le titre n'a pas été scrapé.

    Exemple :
      https://www.parismatch.com/People/isabelle-mergault-avait-adopte-iris-une-deuxieme-petite-fille-266276
      → "people · isabelle mergault avait adopte iris une deuxieme petite fille"

    Inclut la/les sections de path (ex: "People", "actu/societe") en
    préfixe : Voyage utilise ce contexte pour distinguer un article
    People d'un article Sport quand le slug seul est ambigu (ex: les
    deux contiennent un nom propre).
    """
    parsed = urlparse(url or "")
    path = parsed.path or ""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""

    # On prend le dernier segment (= le slug d'article typiquement)
    slug = parts[-1]
    # Retire l'ID numérique final éventuel
    slug = _SLUG_TAIL_NUM_RE.sub("", slug)
    # Remplace tirets/underscores par espaces
    text = re.sub(r"[-_]+", " ", slug).strip()

    # Préfixe = segments intermédiaires (sections), ex: "people" ou
    # "actu societe". On ignore les segments numériques ou la lang ("fr",
    # "en") et on coupe à 2 segments max.
    section_parts: list[str] = []
    for seg in parts[:-1][:2]:
        seg_clean = re.sub(r"[-_]+", " ", seg).strip().lower()
        # Skip lang codes & purement numériques
        if not seg_clean or seg_clean.isdigit():
            continue
        if len(seg_clean) == 2 and seg_clean.isalpha():
            continue  # fr, en, es…
        section_parts.append(seg_clean)

    if section_parts:
        return " · ".join(section_parts) + " · " + text
    return text


def text_for_url(item: dict) -> str:
    """Texte à embedder pour une entrée d'historique.

    Préférence : title (vrai titre éditorial scrapé) > slug nettoyé.
    Garantit JAMAIS de string vide (Voyage rejette les empty strings) :
    fallback final sur l'URL elle-même.
    """
    title = (item.get("title") or "").strip()
    if title:
        return title
    slug_text = slug_to_text(item.get("url", "")).strip()
    if slug_text:
        return slug_text
    # Fallback ultime : l'URL elle-même (jamais vide en pratique)
    url = (item.get("url") or "").strip()
    return url or "untitled"


# ──────────────────────────────────────────────────────────────
# Chemins
# ──────────────────────────────────────────────────────────────


def index_path(project_slug: str) -> Path:
    """data/projects/{slug}/embeddings.npz"""
    return DATA_DIR / "projects" / project_slug / "embeddings.npz"


def meta_path(project_slug: str) -> Path:
    """data/projects/{slug}/embeddings_meta.json — méta lisible humain."""
    return DATA_DIR / "projects" / project_slug / "embeddings_meta.json"


# ──────────────────────────────────────────────────────────────
# Build index
# ──────────────────────────────────────────────────────────────


def build_index(
    project_slug: str,
    *,
    limit: int | None = None,
    backend: str | None = None,
    on_progress=None,
) -> dict[str, Any]:
    """Génère/régénère l'index sémantique d'un projet.

    Args:
        project_slug : projet cible
        limit        : nb max d'URLs à embedder (None = toutes)
        backend      : "voyage" | "tfidf" | None (auto-détection)
        on_progress  : callback(stage, current, total) pour log live

    Returns:
        Dict avec stats : count, backend, dim, used_titles, used_slugs.
    """
    items = load_history(project_slug)
    if limit:
        # Garde les top-clicks pour rester pertinent
        items = sorted(
            items, key=lambda x: x.get("clicks_total", 0), reverse=True
        )[:limit]

    if not items:
        raise RuntimeError(
            f"Aucune URL en base pour '{project_slug}'. "
            f"Lance d'abord gsc-fetch."
        )

    # 1) Préparer les textes
    if on_progress:
        on_progress("prepare", 0, len(items))
    texts: list[str] = []
    used_titles = 0
    used_slugs = 0
    for item in items:
        text = text_for_url(item)
        texts.append(text)
        if item.get("title"):
            used_titles += 1
        else:
            used_slugs += 1

    # 2) Backend : auto-detect ou forcé
    chosen_backend = backend or embeddings.backend_name()

    # 2bis) Pour TF-IDF, fit le vocab sur le corpus complet AVANT d'embedder
    if chosen_backend == "tfidf":
        if on_progress:
            on_progress("fit_tfidf", 0, len(texts))
        embeddings.fit_tfidf(texts)

    # 3) Embedder
    if on_progress:
        on_progress("embed", 0, len(texts))
    vectors, used_backend = embeddings.embed_batch(texts, backend=chosen_backend)
    matrix = np.asarray(vectors, dtype=np.float32)

    # 4) Sauvegarder — on stocke aussi le backend utilisé pour
    # garantir que la search utilise le même (vecteurs incompatibles
    # entre Voyage 1024-dim et TF-IDF 5000-dim sinon).
    if on_progress:
        on_progress("save", 0, 1)
    out_path = index_path(project_slug)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        vectors=matrix,
        urls=np.array([item.get("url", "") for item in items], dtype=object),
        titles=np.array([item.get("title") or "" for item in items], dtype=object),
        clicks=np.array(
            [int(item.get("clicks_total", 0)) for item in items],
            dtype=np.int64,
        ),
        backend=np.array([used_backend], dtype=object),
    )

    # Méta lisible
    meta = {
        "project": project_slug,
        "backend": used_backend,
        "dim": int(matrix.shape[1]),
        "count": int(matrix.shape[0]),
        "used_titles": used_titles,
        "used_slugs": used_slugs,
        "index_file": str(out_path.relative_to(DATA_DIR.parent)),
    }
    meta_path(project_slug).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


# ──────────────────────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────────────────────


def load_index(project_slug: str) -> dict[str, Any]:
    """Charge l'index .npz d'un projet (avec son backend d'origine)."""
    path = index_path(project_slug)
    if not path.exists():
        raise RuntimeError(
            f"Aucun index sémantique pour '{project_slug}'. "
            f"Lance d'abord gsc-embed --project={project_slug}."
        )
    data = np.load(path, allow_pickle=True)
    # Backend : présent dans les nouveaux index, fallback "tfidf" pour
    # les anciens (qui n'avaient pas ce champ)
    if "backend" in data.files:
        backend = str(data["backend"][0])
    else:
        backend = "tfidf"
    return {
        "vectors": data["vectors"],
        "urls": data["urls"],
        "titles": data["titles"],
        "clicks": data["clicks"],
        "backend": backend,
    }


def search_similar(
    project_slug: str,
    query: str,
    *,
    top_k: int = 20,
    backend: str | None = None,
    rerank_by_clicks: bool = False,
) -> list[dict[str, Any]]:
    """Recherche sémantique top-K dans l'historique Discover d'un projet.

    Args:
        project_slug    : projet cible
        query           : texte de recherche (titre de nouveau sujet,
                          thématique, signal faible, etc.)
        top_k           : nb de résultats à retourner
        backend         : backend à utiliser pour la query (par défaut
                          le backend détecté). DOIT correspondre à celui
                          utilisé pour build_index.
        rerank_by_clicks: si True, multiplie la similarity par log(clicks)
                          pour favoriser les contenus qui ont déjà
                          beaucoup performé.

    Returns:
        Liste de dicts {url, title, clicks, similarity, score} triée
        par score décroissant.
    """
    index = load_index(project_slug)
    matrix = index["vectors"]
    urls = index["urls"]
    titles = index["titles"]
    clicks = index["clicks"]

    # Le backend doit matcher celui utilisé pour build l'index
    # (vecteurs Voyage 1024-dim vs TF-IDF 5000-dim incompatibles).
    # On ignore l'argument explicite + l'auto-détection si l'index
    # contient un backend forcé.
    chosen_backend = backend or index.get("backend") or embeddings.backend_name()

    # Pour TF-IDF, le vocab doit avoir été fit sur le même corpus.
    # On le re-fit ici à partir des URLs en base (texts identiques à
    # ceux utilisés pour build_index).
    if chosen_backend == "tfidf":
        items = load_history(project_slug)
        items = sorted(
            items, key=lambda x: x.get("clicks_total", 0), reverse=True
        )[: len(urls)]
        corpus = [text_for_url(it) for it in items]
        embeddings.fit_tfidf(corpus)

    query_vecs, _ = embeddings.embed_batch(
        [query], backend=chosen_backend, use_cache=False
    )
    query_vec = query_vecs[0]

    top_indices = embeddings.cosine_top_k(query_vec, matrix, top_k=top_k * 3 if rerank_by_clicks else top_k)

    results: list[dict[str, Any]] = []
    for idx, sim in top_indices:
        clk = int(clicks[idx])
        if rerank_by_clicks:
            # Boost par log(clicks) — favoriser les performeurs historiques
            boost = np.log1p(clk) / 14.0  # ~1.0 pour 1M clicks
            score = float(sim) * (1.0 + boost)
        else:
            score = float(sim)
        results.append(
            {
                "url": str(urls[idx]),
                "title": str(titles[idx]) or None,
                "clicks": clk,
                "similarity": float(sim),
                "score": score,
            }
        )

    if rerank_by_clicks:
        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[:top_k]

    return results
