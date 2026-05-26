"""Barèmes par signal + pondération finale.

Le CdC liste 5 signaux (Trends, Wiki, X, Google News, GSC). Pour le
POC, on a maintenant 5 sources qui couvrent l'esprit du CdC :
  - Google Trends     ← signal de recherche
  - Wikimedia         ← signal d'audience encyclopédique
  - X Trends          ← signal conversationnel (présence seulement)
  - MSN engagement    ← proxy d'attention médiatique (votes/comments)
  - Discoversnoop     ← signal direct de visibilité Google Discover
                         (= objectif final du produit !)

Pondération POC :
  - Discoversnoop    : 30%  (signal le plus pertinent, direct)
  - Google Trends    : 25%
  - Wikimedia        : 20%
  - MSN engagement   : 15%
  - X Trends         : 10%
  ────────────────────
  Total              : 100%

Chaque sous-score est borné [0, 100]. Le Signal Score final l'est
aussi par construction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------
# Pondérations (sum = 1.0)
# ---------------------------------------------------------------

WEIGHTS = {
    "discover": 0.30,
    "trends": 0.25,
    "wiki": 0.20,
    "msn": 0.15,
    "x": 0.10,
}

# ---------------------------------------------------------------
# Barèmes par signal — saturation log pour éviter qu'un volume
# énorme écrase complètement les autres signaux
# ---------------------------------------------------------------


def _log_saturate(value: float, *, anchor: float, ceiling: float = 100.0) -> float:
    """Échelle log : value=anchor → 80, value=10×anchor → ~95, value=0 → 0.

    Idéal pour des volumes très étalés (search_volume Trends, views Wiki).
    """
    if value <= 0:
        return 0.0
    raw = 80.0 * math.log(1 + value / anchor) / math.log(2)
    return min(ceiling, raw)


def trends_score(search_volume: int | None, percentage_increase: int | None = None) -> float:
    """Score Google Trends.

    - search_volume : volume de recherche (déjà arrondi par SerpAPI)
      anchor = 50 000 → ~80 points
    - bonus % increase si fourni (capé à +15)
    """
    if not search_volume:
        return 0.0

    base = _log_saturate(float(search_volume), anchor=50_000)

    bonus = 0.0
    if percentage_increase:
        try:
            pct = float(percentage_increase)
            # +100% → +5, +500% → +12, +1000% → +15 (capé)
            bonus = min(15.0, 5.0 * math.log10(max(pct, 1.0)))
        except (TypeError, ValueError):
            pass

    return min(100.0, base + bonus)


def wiki_score(views: int | None) -> float:
    """Score Wikimedia.

    - 50 000 vues/jour → ~80 points
    - 300 000 vues/jour → ~100
    """
    if not views:
        return 0.0
    return _log_saturate(float(views), anchor=20_000)


def x_score(rank: int | None) -> float:
    """Score X Trends (basé sur le rang dans la liste, faute de count).

    - rank 1-10   → 80
    - rank 11-30  → 60
    - rank 31-100 → 40
    - rank > 100  → 20
    - absent      → 0
    """
    if rank is None:
        return 0.0
    if rank <= 10:
        return 80.0
    if rank <= 30:
        return 60.0
    if rank <= 100:
        return 40.0
    return 20.0


def discover_score(raw_score: float | None) -> float:
    """Score Discoversnoop.

    Le `score` CSV varie ~0–65 (médian très bas, distribution long
    tail). On sature pour que les rares scores >50 ressortent fort
    sans écraser les sujets intermédiaires.

    Anchor 25 → article à score 25 reçoit ~80 pts.
    """
    if not raw_score or raw_score <= 0:
        return 0.0
    return _log_saturate(float(raw_score), anchor=25)


def msn_score(article: dict) -> float:
    """Score d'engagement MSN — proxy d'attention médiatique.

    Combine votes nets + commentaires. Pas un volume énorme en
    général ; on prend un anchor bas.
    """
    upvotes = int(article.get("upvotes", 0) or 0)
    downvotes = int(article.get("downvotes", 0) or 0)
    comments = int(article.get("comments", 0) or 0)

    # net engagement = votes pondérés + commentaires (commentaires
    # comptent double car ils traduisent un investissement plus fort)
    net = max(0, upvotes - downvotes) + 2 * comments

    # anchor = 50 → ~80 points
    base = _log_saturate(float(net), anchor=50)

    # Plancher de présence : un article qui existe dans MSN sans
    # engagement a quand même un signal de présence éditoriale
    return max(15.0, base) if (upvotes or comments) else max(10.0, base)


# ---------------------------------------------------------------
# Score composite + tier
# ---------------------------------------------------------------


@dataclass(frozen=True)
class ScoreBreakdown:
    """Détail du Signal Score pour audit côté UX."""

    discover: float
    trends: float
    wiki: float
    msn: float
    x: float
    total: float

    def as_dict(self) -> dict:
        return {
            "discover": round(self.discover, 1),
            "trends": round(self.trends, 1),
            "wiki": round(self.wiki, 1),
            "msn": round(self.msn, 1),
            "x": round(self.x, 1),
            "total": round(self.total, 1),
        }


def _convergence_bonus(*subscores: float, threshold: float = 20.0) -> float:
    """Bonus de convergence multi-signaux externes.

    L'intuition : un sujet confirmé par plusieurs sources externes
    (Discover, Trends, Wiki, X) est plus actionnable qu'un sujet à
    un seul signal fort. On ne compte que les signaux externes — pas
    MSN qui est notre base.

    Barème :
      - 1 signal externe   → 0
      - 2 signaux externes → +5
      - 3 signaux externes → +10
      - 4 signaux externes → +15
    """
    confirmed = sum(1 for s in subscores if s >= threshold)
    if confirmed >= 4:
        return 15.0
    if confirmed >= 3:
        return 10.0
    if confirmed == 2:
        return 5.0
    return 0.0


def composite_score(
    *,
    discover: float = 0.0,
    trends: float = 0.0,
    wiki: float = 0.0,
    msn: float = 0.0,
    x: float = 0.0,
) -> ScoreBreakdown:
    """Combine les 5 sous-scores selon les pondérations + bonus convergence."""
    weighted = (
        WEIGHTS["discover"] * discover
        + WEIGHTS["trends"] * trends
        + WEIGHTS["wiki"] * wiki
        + WEIGHTS["msn"] * msn
        + WEIGHTS["x"] * x
    )
    # Le bonus s'applique aux signaux externes uniquement (pas MSN)
    bonus = _convergence_bonus(discover, trends, wiki, x)
    total = min(100.0, weighted + bonus)
    return ScoreBreakdown(
        discover=discover, trends=trends, wiki=wiki, msn=msn, x=x, total=total
    )


def tier_from_score(score: float) -> str:
    """Mêmes seuils que côté front (cf scripts/data.js).

    Calibrés pour le POC avec les 4 sources actuelles. Le CdC vise des
    seuils 70/40 mais c'est calibré pour 5 sources (avec GSC + Google
    News dédiés). En attendant la Phase 1, on relâche.
    """
    if score >= 50:
        return "high"
    if score >= 30:
        return "medium"
    return "low"
