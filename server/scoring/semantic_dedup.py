"""Deduplication semantique cross-source des candidats scores.

Probleme resolu : aujourd'hui, le matcher Jaccard ne reconnait pas que
"PSG remporte la Ligue des champions" et "Les Parisiens sacres champions
d'Europe" sont le meme evenement (zero token en commun). Ces deux MSN
articles deviennent deux sujets distincts dans le top-30, polluant le
classement avec des doublons.

Solution : on embed (Voyage AI) chaque candidat MSN apres scoring, et
on cluster par cosine similarity > seuil. Pour chaque cluster, on garde
le meilleur score comme representant et on enrichit avec les titres
alternatifs des membres.

Cout typique : ~80 articles MSN par run x 4 runs/jour x ~50 tokens =
16k tokens/jour. Tarif Voyage : $0.06/Mtok -> ~$0.001/jour. Negligeable.

Cache automatique par hash(text) dans server/scoring/embeddings.py.

Si Voyage non configure, le module degrade gracieusement (fallback
TF-IDF si fit_tfidf appele, sinon pas de dedup).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from server.scoring import embeddings

# Seuil cosine pour considerer deux articles comme le meme evenement.
# Calibre sur voyage-3 multilingue : 0.78 capte les vrais doublons
# (meme info sous des titres differents) sans regrouper des sujets
# proches mais distincts. A descendre si on observe trop de "presque
# duplicates" qui restent, a remonter si on fusionne a tort.
SIMILARITY_THRESHOLD = 0.78


def _embed_text_for_article(article: dict[str, Any]) -> str:
    """Texte representatif a embedder pour un article MSN.

    On combine titre + premiere phrase du snippet (~150 chars) pour
    avoir assez de signal sans noyer dans du texte fonctionnel.
    """
    title = (article.get("title") or "").strip()
    snippet = (article.get("snippet") or "").strip()
    if snippet:
        # Premiere phrase ou 200 chars max
        first_sentence = snippet.split(".", 1)[0][:200]
        return f"{title}. {first_sentence}"
    return title


def cluster_scored_candidates(
    scored: list[dict[str, Any]],
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    """Cluster les candidats scores par similarite semantique.

    Pour chaque cluster, retourne le meilleur scored + enrichit avec
    `cluster_size` (nb members) et `cluster_members_titles` (titres
    alternatifs pour affichage).

    Args:
        scored : liste de candidats deja scores par aggregator.
                 Chaque item doit contenir "msn_article" + "breakdown".
        threshold : cosine similarity minimum pour fusion.

    Returns:
        Liste reduite de candidats, tries par score (meilleur d'abord),
        avec annotations cluster_*.
    """
    if not scored:
        return []

    # Tri prealable par score (meilleur d'abord) — important pour que
    # le representant de cluster soit toujours le mieux score.
    sorted_scored = sorted(
        scored, key=lambda s: s["breakdown"].total, reverse=True
    )

    # Texte a embedder pour chacun
    texts = [_embed_text_for_article(s["msn_article"]) for s in sorted_scored]

    try:
        vectors, backend = embeddings.embed_batch(texts)
    except Exception as exc:  # noqa: BLE001
        # Voyage indispo (cle absente, reseau, quota) : on degrade en
        # mode no-op. Pas de dedup mais le pipeline continue.
        print(
            f"[semantic_dedup] embeddings KO ({type(exc).__name__}: {exc}) — "
            "skip dedup (pas de clustering)"
        )
        for s in sorted_scored:
            s["cluster_size"] = 1
            s["cluster_members_titles"] = []
        return sorted_scored

    matrix = np.asarray(vectors, dtype=np.float32)
    # L2 norme pour cosine simple
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    matrix_n = matrix / norms

    # Greedy agglomeratif : on parcourt dans l'ordre du score, chaque
    # article rejoint le 1er cluster existant avec sim > threshold,
    # sinon il fonde un nouveau cluster.
    cluster_reps: list[int] = []  # indices dans sorted_scored des representants
    cluster_members: dict[int, list[int]] = {}  # rep_idx -> list of member idx

    for i in range(len(sorted_scored)):
        joined = False
        for rep_idx in cluster_reps:
            sim = float(matrix_n[i] @ matrix_n[rep_idx])
            if sim >= threshold:
                cluster_members[rep_idx].append(i)
                joined = True
                break
        if not joined:
            cluster_reps.append(i)
            cluster_members[i] = [i]

    # Construit le resultat : 1 entree par cluster (le representant)
    # enrichi des titres des autres membres.
    result: list[dict[str, Any]] = []
    for rep_idx in cluster_reps:
        rep = sorted_scored[rep_idx]
        members = cluster_members[rep_idx]
        member_titles = [
            sorted_scored[m]["msn_article"].get("title", "")
            for m in members
            if m != rep_idx
        ]
        rep["cluster_size"] = len(members)
        rep["cluster_members_titles"] = member_titles
        result.append(rep)

    n_clusters = len(result)
    n_originals = len(sorted_scored)
    if n_clusters < n_originals:
        print(
            f"[semantic_dedup] {n_originals} candidats -> {n_clusters} "
            f"clusters (fusion de {n_originals - n_clusters} doublons "
            f"semantiques, backend={backend})"
        )

    return result
