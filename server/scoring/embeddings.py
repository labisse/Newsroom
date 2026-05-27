"""Service d'embeddings — Voyage AI avec fallback TF-IDF stdlib.

Deux backends :
  1. Voyage API (voyage-3 par défaut) si VOYAGE_API_KEY défini.
     Multilingue, qualité élevée, ~$0.06 / 1M tokens.
  2. TF-IDF pur numpy — fallback gratuit. Qualité moindre mais
     suffisante pour démarrer / tester / matcher des sujets très
     proches.

Cache disque par hash(text) pour éviter les recalculs et économiser
les appels API.

Port adapté de Audit Discover (services/semantic/embeddings_service.py).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import requests

from server.config import DATA_DIR, settings

# ──────────────────────────────────────────────────────────────
# Cache disque
# ──────────────────────────────────────────────────────────────

_CACHE_DIR = DATA_DIR / "cache" / "embeddings"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _hash_text(text: str, backend: str) -> str:
    """Hash unique par (text, backend) — chaque backend produit des
    vecteurs de dimensions différentes, on ne mélange pas les caches."""
    blob = f"{backend}::{text}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:24]


def _cache_path(h: str) -> Path:
    return _CACHE_DIR / f"{h}.json"


def _cache_get(h: str) -> list[float] | None:
    path = _cache_path(h)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None


def _cache_put(h: str, vec: list[float]) -> None:
    try:
        _cache_path(h).write_text(json.dumps(vec), encoding="utf-8")
    except IOError:
        pass


# ──────────────────────────────────────────────────────────────
# Backend Voyage
# ──────────────────────────────────────────────────────────────

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_BATCH_SIZE = 128  # limite API
VOYAGE_TIMEOUT_S = 60


def _voyage_embed(texts: list[str]) -> list[list[float]]:
    """Appel batch à Voyage API. Voyage rejette les empty strings :
    on remplace par "untitled" pour ne jamais planter le batch."""
    if not settings.voyage_api_key:
        raise RuntimeError("VOYAGE_API_KEY manquant")

    # Sanitize : pas d'empty string dans le payload Voyage
    safe_texts = [(t or "").strip() or "untitled" for t in texts]

    out: list[list[float]] = []
    for i in range(0, len(safe_texts), VOYAGE_BATCH_SIZE):
        chunk = safe_texts[i : i + VOYAGE_BATCH_SIZE]
        response = requests.post(
            VOYAGE_URL,
            headers={
                "Authorization": f"Bearer {settings.voyage_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input": chunk,
                "model": settings.voyage_model,
                "input_type": "document",
            },
            timeout=VOYAGE_TIMEOUT_S,
        )
        if response.status_code >= 400:
            try:
                err = response.json().get("error", {}).get("message", response.text)
            except (json.JSONDecodeError, ValueError):
                err = response.text
            raise RuntimeError(f"Voyage error ({response.status_code}): {err}")

        data = response.json()
        for item in data.get("data", []):
            out.append(item["embedding"])
    return out


# ──────────────────────────────────────────────────────────────
# Backend TF-IDF stdlib
# ──────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"\b[\wÀ-ÿ]+\b", re.UNICODE)
_TFIDF_VOCAB: dict[str, int] = {}  # mot → index
_TFIDF_IDF: dict[str, float] = {}  # mot → IDF
_TFIDF_DIM = 0  # dimension du vecteur


def _tokenize(text: str) -> list[str]:
    """Tokenize FR : lowercase + extraction de mots (lettres + chiffres)."""
    return _TOKEN_RE.findall((text or "").lower())


def fit_tfidf(corpus: list[str], *, min_df: int = 2, max_vocab: int = 5000) -> None:
    """Construit le vocabulaire + IDF à partir d'un corpus.

    À appeler UNE FOIS sur tout le corpus avant d'embedder.
    Le vocab et l'IDF sont stockés en globals pour les appels suivants.
    """
    global _TFIDF_VOCAB, _TFIDF_IDF, _TFIDF_DIM

    df: Counter = Counter()  # nb docs où le mot apparaît
    for text in corpus:
        tokens = set(_tokenize(text))
        for token in tokens:
            df[token] += 1

    n_docs = len(corpus) or 1
    # Filtrer rares + trier par df descendant
    selected = [
        (word, count)
        for word, count in df.most_common(max_vocab)
        if count >= min_df
    ]

    _TFIDF_VOCAB = {word: i for i, (word, _) in enumerate(selected)}
    _TFIDF_IDF = {
        word: math.log((n_docs + 1) / (count + 1)) + 1.0
        for word, count in selected
    }
    _TFIDF_DIM = len(_TFIDF_VOCAB)


def _tfidf_embed_one(text: str) -> list[float]:
    """Vecteur TF-IDF L2-normalisé pour un texte."""
    if not _TFIDF_VOCAB:
        raise RuntimeError(
            "TF-IDF non initialisé. Appelle fit_tfidf(corpus) avant d'embedder."
        )
    tokens = _tokenize(text)
    tf: Counter = Counter(tokens)
    vec = np.zeros(_TFIDF_DIM, dtype=np.float32)
    for token, count in tf.items():
        idx = _TFIDF_VOCAB.get(token)
        if idx is None:
            continue
        vec[idx] = count * _TFIDF_IDF.get(token, 0.0)
    # L2-normalisation
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


def _tfidf_embed(texts: list[str]) -> list[list[float]]:
    return [_tfidf_embed_one(t) for t in texts]


# ──────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────


def backend_name() -> str:
    """Retourne 'voyage' si clé dispo, sinon 'tfidf'."""
    return "voyage" if settings.voyage_api_key else "tfidf"


def embed_batch(
    texts: list[str],
    *,
    backend: str | None = None,
    use_cache: bool = True,
) -> tuple[list[list[float]], str]:
    """Embedde un batch de textes. Retourne (vectors, backend_used).

    - Cache automatique par hash(text, backend).
    - Préserve l'ordre d'entrée.
    """
    backend = backend or backend_name()
    if backend not in ("voyage", "tfidf"):
        raise ValueError(f"backend inconnu : {backend}")

    n = len(texts)
    out: list[list[float] | None] = [None] * n
    to_compute: list[tuple[int, str]] = []  # (index, text)

    # 1) Cache lookup
    if use_cache:
        for i, text in enumerate(texts):
            h = _hash_text(text, backend)
            cached = _cache_get(h)
            if cached is not None:
                out[i] = cached
            else:
                to_compute.append((i, text))
    else:
        to_compute = list(enumerate(texts))

    # 2) Compute missing
    if to_compute:
        missing_texts = [t for _, t in to_compute]
        if backend == "voyage":
            vecs = _voyage_embed(missing_texts)
        else:
            vecs = _tfidf_embed(missing_texts)

        for (idx, text), vec in zip(to_compute, vecs):
            out[idx] = vec
            if use_cache:
                _cache_put(_hash_text(text, backend), vec)

    # Sanity
    assert all(v is not None for v in out), "Embedding manquant"
    return out, backend  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────
# Recherche cosine
# ──────────────────────────────────────────────────────────────


def cosine_top_k(
    query_vec: list[float],
    matrix: np.ndarray,
    *,
    top_k: int = 20,
) -> list[tuple[int, float]]:
    """Retourne les top_k indices + similarités cosine.

    Args:
        query_vec : vecteur de la query (list[float])
        matrix    : matrice (N, D) des vecteurs candidats
        top_k     : nb de résultats à retourner

    Returns:
        Liste de (index, similarity) triée par similarité décroissante.
    """
    if matrix.size == 0:
        return []

    q = np.asarray(query_vec, dtype=np.float32)
    q_norm = float(np.linalg.norm(q)) or 1e-9

    # Les vecteurs en matrix peuvent ne pas être normalisés (Voyage)
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1) + 1e-9

    with np.errstate(divide="ignore", invalid="ignore"):
        sims = (matrix @ q) / (norms * q_norm)
    # Remplace les NaN éventuels (vecteurs nuls) par 0
    sims = np.nan_to_num(sims, nan=0.0, posinf=0.0, neginf=0.0)
    # Top-k via argpartition (O(N) au lieu de O(N log N))
    k = min(top_k, len(sims))
    idx = np.argpartition(-sims, k - 1)[:k]
    idx = idx[np.argsort(-sims[idx])]  # tri stable des top-k
    return [(int(i), float(sims[i])) for i in idx]
