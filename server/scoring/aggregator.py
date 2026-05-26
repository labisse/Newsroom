"""Agrégateur — produit la liste des sujets scorés à partir des 4 sources.

Stratégie v1 :
  - chaque article MSN est un candidat de sujet
  - pour chaque candidat, on cherche le meilleur match dans :
      * Google Trends (fenêtre `current`)
      * Wikimedia top pageviews
      * X Trends
  - on calcule les 4 sous-scores + le composite
  - on garde le top N par score décroissant

Format de sortie aligné avec ce que consomme le front (cf
scripts/data.js mock). Champs clés : id, rank, title, theme, score,
tier, rationale, signals[], sources (détail pour expand), refs[].
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server.config import DATA_DIR
from server.scoring import score as scoring
from server.scoring.matcher import Match, best_match
from server.scoring.normalize import token_set
from server.sources._common import now_iso, today_str, write_snapshot

TOP_N = 30  # nombre de sujets retenus dans la sortie finale

# ---------------------------------------------------------------
# Chargement des snapshots
# ---------------------------------------------------------------


def _load(source: str) -> dict[str, Any]:
    path = DATA_DIR / source / "latest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Snapshot manquant : {path}. Lance d'abord `python -m server.cli fetch-all`"
        )
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------
# Préparation des candidats pour matching
# ---------------------------------------------------------------


def _prepare_trends(gt_payload: dict, x_payload: dict) -> tuple[list[dict], list[dict]]:
    """Aplatit Google Trends (fenêtre current) et X Trends en candidats."""
    gt = gt_payload.get("windows", {}).get("current", {}).get("trends", [])
    x = x_payload.get("trends", [])

    # X Trends : on ajoute un `rank` 1-indexed pour le scoring par rang
    x_with_rank = [
        {**t, "rank": i + 1, "query": t.get("query", "")}
        for i, t in enumerate(x)
    ]
    return gt, x_with_rank


def _prepare_wiki(wiki_payload: dict) -> list[dict]:
    """Wikimedia : on garde title_display pour matching."""
    return wiki_payload.get("articles", [])


# ---------------------------------------------------------------
# Génération de la phrase rationale
# ---------------------------------------------------------------


def _rationale(
    msn_article: dict,
    trends_match: Match | None,
    wiki_match: Match | None,
    x_match: Match | None,
    breakdown: scoring.ScoreBreakdown,
) -> str:
    """Phrase explicative générée pour le rédac chef."""
    parts: list[str] = []

    if trends_match and breakdown.trends >= 60:
        vol = trends_match.target.get("search_volume", 0)
        parts.append(f"Pic Google Trends ({vol:,} recherches)".replace(",", " "))
    elif trends_match:
        parts.append("Présent sur Google Trends")

    if wiki_match and breakdown.wiki >= 60:
        views = wiki_match.target.get("views", 0)
        parts.append(
            f"forte audience Wikipedia ({views:,} vues/jour)".replace(",", " ")
        )
    elif wiki_match:
        parts.append("présent dans le top Wikipedia")

    if x_match and breakdown.x >= 60:
        parts.append("trending sur X")
    elif x_match:
        parts.append("mentionné sur X")

    if breakdown.msn >= 60:
        parts.append("engagement MSN élevé")

    if not parts:
        return "Présence éditoriale MSN sans signal de tendance externe."

    # Capitaliser la première lettre, joindre par " · "
    text = " · ".join(parts) + "."
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------
# Construction d'un sujet
# ---------------------------------------------------------------


def _build_signals(
    trends_match: Match | None,
    wiki_match: Match | None,
    x_match: Match | None,
    msn_article: dict,
) -> list[dict[str, Any]]:
    """Construit la liste de signal pills affichée dans le front."""
    signals: list[dict[str, Any]] = []

    if trends_match:
        vol = trends_match.target.get("search_volume", 0)
        signals.append(
            {
                "source": "trends",
                "label": "trends",
                "value": _format_volume(vol),
            }
        )

    if wiki_match:
        views = wiki_match.target.get("views", 0)
        signals.append(
            {
                "source": "wiki",
                "label": "wiki",
                "value": _format_volume(views, suffix="vues"),
            }
        )

    if x_match:
        rank = x_match.target.get("rank", 0)
        signals.append(
            {
                "source": "x",
                "label": "x",
                "value": f"#{rank}" if rank else "trending",
            }
        )

    # Toujours indiquer MSN puisque c'est la base
    engagement = (msn_article.get("upvotes", 0) or 0) + (
        msn_article.get("comments", 0) or 0
    )
    if engagement > 0:
        signals.append(
            {
                "source": "news",
                "label": "msn",
                "value": f"{engagement}+ react.",
            }
        )

    return signals


def _format_volume(v: int, suffix: str = "") -> str:
    """200000 → '200k', 1500000 → '1.5M'."""
    if not v:
        return "—"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M{(' ' + suffix) if suffix else ''}"
    if v >= 1_000:
        return f"{v/1_000:.0f}k{(' ' + suffix) if suffix else ''}"
    return f"{v}{(' ' + suffix) if suffix else ''}"


def _build_sources_detail(
    trends_match: Match | None,
    wiki_match: Match | None,
    x_match: Match | None,
    breakdown: scoring.ScoreBreakdown,
) -> list[dict[str, Any]]:
    """Détail par source pour l'expand row du front (bars de progression)."""
    return [
        {
            "name": "Google Trends",
            "value": (
                _format_volume(trends_match.target.get("search_volume", 0))
                if trends_match
                else "—"
            ),
            "fill": int(breakdown.trends),
        },
        {
            "name": "Wikimedia",
            "value": (
                _format_volume(wiki_match.target.get("views", 0), suffix="vues/h")
                if wiki_match
                else "—"
            ),
            "fill": int(breakdown.wiki),
        },
        {
            "name": "X velocity",
            "value": (
                f"rang #{x_match.target.get('rank')}"
                if x_match
                else "—"
            ),
            "fill": int(breakdown.x),
        },
        {
            "name": "MSN engagement",
            "value": f"{breakdown.msn:.0f}/100",
            "fill": int(breakdown.msn),
        },
    ]


def _score_article(
    msn_article: dict,
    *,
    gt_candidates: list[dict],
    wiki_candidates: list[dict],
    x_candidates: list[dict],
) -> dict[str, Any] | None:
    """Score un article MSN. Retourne None si titre vide."""
    title = msn_article.get("title", "")
    if not title:
        return None

    src_tokens = token_set(title)
    if not src_tokens:
        return None

    trends_match = best_match(src_tokens, gt_candidates, title_key="query")
    wiki_match = best_match(src_tokens, wiki_candidates, title_key="title_display")
    x_match = best_match(src_tokens, x_candidates, title_key="query")

    breakdown = scoring.composite_score(
        trends=(
            scoring.trends_score(
                trends_match.target.get("search_volume"),
                trends_match.target.get("percentage_increase"),
            )
            if trends_match
            else 0.0
        ),
        wiki=(
            scoring.wiki_score(wiki_match.target.get("views"))
            if wiki_match
            else 0.0
        ),
        msn=scoring.msn_score(msn_article),
        x=(scoring.x_score(x_match.target.get("rank")) if x_match else 0.0),
    )

    return {
        "msn_article": msn_article,
        "trends_match": trends_match,
        "wiki_match": wiki_match,
        "x_match": x_match,
        "breakdown": breakdown,
    }


def _to_sujet_dict(scored: dict[str, Any], rank: int) -> dict[str, Any]:
    """Convertit un score en sujet prêt à sérialiser pour le front."""
    article = scored["msn_article"]
    breakdown: scoring.ScoreBreakdown = scored["breakdown"]

    rationale = _rationale(
        article,
        scored["trends_match"],
        scored["wiki_match"],
        scored["x_match"],
        breakdown,
    )

    signals = _build_signals(
        scored["trends_match"],
        scored["wiki_match"],
        scored["x_match"],
        article,
    )

    sources_detail = _build_sources_detail(
        scored["trends_match"],
        scored["wiki_match"],
        scored["x_match"],
        breakdown,
    )

    refs: list[str] = []
    if article.get("url"):
        refs.append(
            f"MSN · {article.get('source', 'MSN')} — {article['title']}"
        )

    rounded = int(round(breakdown.total))
    return {
        "id": f"s{rank:02d}",
        "rank": rank,
        "title": article["title"],
        "theme": article.get("category") or "actualité",
        "score": rounded,
        # Classement basé sur le score visible : un sujet affiché à 50
        # doit être en "high" même si son exact est 49.5
        "tier": scoring.tier_from_score(rounded),
        "rationale": rationale,
        "signals": signals,
        "sources": sources_detail,
        "score_breakdown": breakdown.as_dict(),
        "msn_url": article.get("url"),
        "msn_image": article.get("image_url"),
        "msn_source_name": article.get("source"),
        "refs": refs,
    }


# ---------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------


def aggregate(top_n: int = TOP_N) -> dict[str, Any]:
    """Pipeline complet. Retourne le payload final prêt à écrire."""
    msn = _load("msn")
    wikimedia = _load("wikimedia")
    gt = _load("google_trends")
    x = _load("x_trends")

    gt_candidates, x_candidates = _prepare_trends(gt, x)
    wiki_candidates = _prepare_wiki(wikimedia)

    scored: list[dict[str, Any]] = []
    for article in msn.get("articles", []):
        result = _score_article(
            article,
            gt_candidates=gt_candidates,
            wiki_candidates=wiki_candidates,
            x_candidates=x_candidates,
        )
        if result is not None:
            scored.append(result)

    # Tri par score total décroissant
    scored.sort(key=lambda s: s["breakdown"].total, reverse=True)
    top = scored[:top_n]

    sujets = [_to_sujet_dict(s, rank=i + 1) for i, s in enumerate(top)]

    # Comptage par tier (utile pour les pills du hero)
    counts = {"high": 0, "medium": 0, "low": 0}
    for s in sujets:
        counts[s["tier"]] += 1

    return {
        "generated_at": now_iso(),
        "sources_used": {
            "msn": {"fetched_at": msn.get("fetched_at"), "count": msn.get("count")},
            "wikimedia": {
                "fetched_at": wikimedia.get("fetched_at"),
                "count": wikimedia.get("count"),
            },
            "google_trends": {
                "fetched_at": gt.get("fetched_at"),
                "count": gt.get("windows", {}).get("current", {}).get("count"),
            },
            "x_trends": {"fetched_at": x.get("fetched_at"), "count": x.get("count")},
        },
        "weights": scoring.WEIGHTS,
        "totals": {
            "candidates_scored": len(scored),
            "kept": len(sujets),
            "by_tier": counts,
        },
        "sujets": sujets,
    }


def run(top_n: int = TOP_N) -> dict[str, Any]:
    payload = aggregate(top_n=top_n)
    write_snapshot("sujets", payload, today_str())
    return payload
