"""Matching de signaux par Jaccard sur tokens.

On ne fait pas de stemming ni d'embeddings : pour du titre court FR,
le Jaccard sur tokens normalisés produit déjà des matches très
acceptables et reste déterministe + auditable (le rédac chef peut
comprendre pourquoi tel sujet matche tel signal).

Stratégie :
  - on calcule Jaccard = |A ∩ B| / |A ∪ B|
  - on accepte un match si Jaccard ≥ threshold (défaut 0.3)
  - on retourne aussi les matches sub-threshold mais avec ≥ 2 tokens
    en commun (utile pour les sujets multi-mots où Jaccard est dilué
    par les longues queries)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from server.scoring.normalize import token_set


def jaccard(a: set[str], b: set[str]) -> float:
    """Similarité de Jaccard entre deux sets de tokens. 0 si l'un est vide."""
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    return len(inter) / len(union)


@dataclass(frozen=True)
class Match:
    """Un match entre un titre source et une cible (trend, page wiki, …)."""

    target: dict
    score: float
    common_tokens: tuple[str, ...]


def best_match(
    source_tokens: set[str],
    candidates: Iterable[dict],
    *,
    title_key: str,
    threshold: float = 0.3,
    min_common: int = 2,
) -> Match | None:
    """Trouve le meilleur match parmi des candidats.

    Args:
        source_tokens: tokens du titre source (article MSN typiquement)
        candidates: liste de dicts (trends, pages wiki, etc.)
        title_key: clé contenant le titre dans chaque candidat
        threshold: Jaccard minimal pour valider un match
        min_common: nombre minimal de tokens en commun (fallback si
                    Jaccard est sub-threshold à cause de candidats longs)
    """
    best: Match | None = None

    for cand in candidates:
        title = cand.get(title_key) or ""
        cand_tokens = token_set(title)
        if not cand_tokens:
            continue

        common = source_tokens & cand_tokens
        score = jaccard(source_tokens, cand_tokens)

        passes = score >= threshold or len(common) >= min_common
        if not passes:
            continue

        if best is None or score > best.score:
            best = Match(
                target=cand,
                score=score,
                common_tokens=tuple(sorted(common)),
            )

    return best
