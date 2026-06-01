"""Heuristique predictive Discover (B1 etape 1).

Pour chaque sujet, on calcule une probabilite estimee qu'il atterrisse
dans Google Discover dans les 24-48h. Cette heuristique est explicite
(pas de ML) — elle servira de placeholder jusqu'a ce qu'on ait assez
de training data accumulee via discover_labeler pour entrainer un vrai
modele (~30-60 jours d'historique).

Calibration empirique sur le hit rate global observe (~12% sur les
premieres mesures, B1 etape 2). Les coefficients sont ajustables.

Output par sujet :
  {
    "proba": 0.65,            # 0-1, probabilite estimee
    "confidence": "high",     # high / medium / low
    "factors": ["..."],       # liste lisible des facteurs majeurs
  }

Quand on aura un modele entraine, on remplacera score_proba() par
l'inference du modele sans toucher au reste du pipeline (aggregator
appelle predictor.score_proba(sujet), c'est tout).
"""

from __future__ import annotations

from typing import Any


def _signals_in_sujet(sujet: dict[str, Any]) -> set[str]:
    """Set des sources qui ont contribue au scoring (depuis 'signals')."""
    sigs = sujet.get("signals") or []
    out: set[str] = set()
    for s in sigs:
        label = s.get("label") or s.get("source") or ""
        if label:
            out.add(label.lower())
    return out


def _base_from_convergence(sources: set[str], n_signals: int) -> tuple[float, str]:
    """Score de base selon la convergence multi-source.

    Logique : plus le sujet est present sur des sources qualitatives
    (msn, gnews, wiki, discover), plus la proba est haute.
    """
    has_discover = "discover" in sources
    has_msn = "msn" in sources
    has_gnews = "gnews" in sources
    has_wiki = "wiki" in sources
    has_trends = "trends" in sources

    # Deja sur Discover : base solide mais on laisse room pour
    # differencier via les multiplicateurs (winner certain vs candidat).
    # Note : "deja sur Discover" = present sur l'agregateur Discoversnoop
    # global, pas forcement sur le site d'un projet specifique.
    if has_discover:
        return 0.65, "deja indexe par Discover (global)"

    # Trio editorial fort : msn + gnews + (wiki ou trends) = info qui
    # tourne sur les vrais medias avec validation Wikipedia/Trends.
    # C'est typiquement un sujet qui va emerger sur Discover dans 24h.
    if has_msn and has_gnews and (has_wiki or has_trends):
        return 0.50, "convergence editoriale forte (MSN+GNews+Wiki/Trends)"

    # Duo editorial : msn + gnews (= sujet d'actu confirme par 2
    # sources qualitatives mais sans encore signal historique)
    if has_msn and has_gnews:
        return 0.35, "duo editorial (MSN+GNews)"

    # Multi-source quelconque : >= 4 sources mais sans le duo qualite
    if n_signals >= 4:
        return 0.25, "multi-source (≥4 sources)"

    # 2-3 sources : signal moyen
    if n_signals >= 2:
        return 0.12, "convergence partielle"

    # Isole : faible signal
    return 0.05, "signal isole"


def _trend_multiplier(sujet: dict[str, Any]) -> tuple[float, str | None]:
    """Multiplicateur lie au trend velocity_6h.

    Un sujet qui monte rapidement est plus susceptible d'atterrir sur
    Discover qu'un sujet stable ou en chute.
    """
    trend = sujet.get("trend") or "new"
    v6 = sujet.get("velocity_6h")

    if trend == "rising":
        # +25% si forte velocity, +15% sinon
        if v6 is not None and v6 >= 10:
            return 1.25, "↗ monte rapidement (+25%)"
        return 1.15, "↗ en hausse (+15%)"
    if trend == "falling":
        # -20% car le pic est passe
        return 0.80, "↘ en chute (-20%)"
    # stable / new : pas de bonus ni malus
    return 1.00, None


def _cluster_multiplier(sujet: dict[str, Any]) -> tuple[float, str | None]:
    """Bonus si plusieurs articles MSN traitent le meme evenement.

    Un cluster_size > 1 indique que des medias differents publient
    sur le sujet → indicateur d'evenement editorialement chaud.
    """
    n = int(sujet.get("cluster_size") or 1)
    if n >= 3:
        return 1.15, f"×{n} articles fusionnes (+15%)"
    if n >= 2:
        return 1.08, f"×{n} articles fusionnes (+8%)"
    return 1.00, None


def _ton_multiplier(sujet: dict[str, Any]) -> tuple[float, str | None]:
    """Bonus selon le ton editorial detecte par le LLM.

    Discover privilege les contenus actuels et factuels. Le ton
    'polemique' (controverse) genere aussi beaucoup de clics.
    Le ton 'opinion' ou 'divers' est moins Discover-friendly.
    """
    enrich = sujet.get("llm_enrich") or {}
    ton = (enrich.get("ton") or "factuel").lower()
    if ton == "polemique":
        return 1.10, "ton polemique (+10%)"
    if ton == "factuel":
        return 1.05, "ton factuel (+5%)"
    if ton == "people":
        return 1.08, "people/celebrites (+8%)"
    if ton == "opinion":
        return 0.92, "ton opinion (-8%)"
    return 1.00, None


def _score_multiplier(sujet: dict[str, Any]) -> tuple[float, str | None]:
    """Bonus selon le score composite global (0-100).

    Plus le score est haut, plus on fait confiance au signal.
    """
    score = int(sujet.get("score") or 0)
    if score >= 80:
        return 1.20, f"score eleve {score} (+20%)"
    if score >= 60:
        return 1.10, f"score solide {score} (+10%)"
    if score >= 40:
        return 1.00, None
    return 0.90, f"score faible {score} (-10%)"


def _confidence_from_proba(proba: float, n_signals: int) -> str:
    """Niveau de confiance affiche en UI.

    high : proba >= 60% ET >= 3 sources (= signal coherent multi-source)
    medium : proba >= 30% OU >= 2 sources
    low : reste
    """
    if proba >= 0.60 and n_signals >= 3:
        return "high"
    if proba >= 0.30 or n_signals >= 2:
        return "medium"
    return "low"


def score_proba(sujet: dict[str, Any]) -> dict[str, Any]:
    """Calcule la probabilite Discover heuristique pour un sujet.

    Args:
        sujet : dict du sujet apres scoring + enrich (avec signals,
                trend, velocity_6h, cluster_size, llm_enrich, etc.)

    Returns:
        {
            "proba": float in [0, 1],
            "confidence": "high" / "medium" / "low",
            "factors": list[str],  # facteurs lisibles pour debug/UI
        }
    """
    sources = _signals_in_sujet(sujet)
    n_signals = len(sujet.get("signals") or [])

    base, base_reason = _base_from_convergence(sources, n_signals)
    factors: list[str] = [base_reason]

    proba = base

    # Multiplicateurs successifs
    for mult_fn in (
        _trend_multiplier,
        _cluster_multiplier,
        _ton_multiplier,
        _score_multiplier,
    ):
        mult, reason = mult_fn(sujet)
        proba *= mult
        if reason:
            factors.append(reason)

    # Clamp + arrondi
    proba = max(0.0, min(1.0, proba))
    proba = round(proba, 3)

    return {
        "proba": proba,
        "confidence": _confidence_from_proba(proba, n_signals),
        "factors": factors,
    }


def annotate(payload: dict[str, Any]) -> dict[str, Any]:
    """Annote tous les sujets d'un payload avec discover_prediction.

    Modifie en place + retourne le meme payload. Idempotent.
    """
    sujets = payload.get("sujets") or []
    for s in sujets:
        s["discover_prediction"] = score_proba(s)
    return payload
