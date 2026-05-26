"""Barèmes par signal + pondération finale.

Conformément au CdC (section 4.2) mais adapté au POC :
  - GSC historique : non branché (CSV manuel reporté en Phase 1)
  - Google News : non branché — MSN sert de proxy d'attention médiatique

Pondération POC :
  - Google Trends    : 35%  (CdC original 30%)
  - Wikimedia        : 25%  (CdC original 20%)
  - MSN engagement   : 25%  (proxy Google News + GSC)
  - X Trends presence: 15%  (CdC original 20%, downgrade car
                              trends24.in n'expose plus le tweet_count)
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
    "trends": 0.35,
    "wiki": 0.25,
    "msn": 0.25,
    "x": 0.15,
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

    trends: float
    wiki: float
    msn: float
    x: float
    total: float

    def as_dict(self) -> dict:
        return {
            "trends": round(self.trends, 1),
            "wiki": round(self.wiki, 1),
            "msn": round(self.msn, 1),
            "x": round(self.x, 1),
            "total": round(self.total, 1),
        }


def composite_score(
    *,
    trends: float = 0.0,
    wiki: float = 0.0,
    msn: float = 0.0,
    x: float = 0.0,
) -> ScoreBreakdown:
    """Combine les 4 sous-scores selon les pondérations."""
    total = (
        WEIGHTS["trends"] * trends
        + WEIGHTS["wiki"] * wiki
        + WEIGHTS["msn"] * msn
        + WEIGHTS["x"] * x
    )
    return ScoreBreakdown(trends=trends, wiki=wiki, msn=msn, x=x, total=total)


def tier_from_score(score: float) -> str:
    """Mêmes seuils que côté front (cf scripts/data.js)."""
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"
