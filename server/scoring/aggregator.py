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
from server.scoring import clusters as clustering
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


def _load_optional(source: str) -> dict[str, Any]:
    """Comme _load, mais renvoie {} si le snapshot manque. Pour les
    sources récentes (Reddit, YouTube) qui peuvent ne pas être présentes
    au premier run et ne doivent pas casser le pipeline."""
    path = DATA_DIR / source / "latest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


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


def _prepare_discover(payload: dict) -> list[dict]:
    """Discoversnoop : articles avec score, on les retourne tels quels.

    Le matching utilise déjà le champ `title` côté Jaccard, pas besoin
    de transformation.
    """
    return payload.get("articles", [])


def _prepare_gnews(payload: dict) -> list[dict]:
    """Google News : articles RSS dédupliqués, on les retourne tels quels."""
    return payload.get("articles", [])


def _prepare_reddit(payload: dict) -> list[dict]:
    """Reddit : posts dédupliqués cross-subs.

    Le `cross_subs_count` est porté par le post lui-même (cf reddit.py),
    on l'utilise comme proxy de viralité au moment du matching.
    """
    return payload.get("posts", []) if payload else []


def _prepare_youtube(payload: dict) -> list[dict]:
    """YouTube Trending : vidéos déjà triées par velocity."""
    return payload.get("videos", []) if payload else []


def _count_matches(
    source_tokens: set,
    candidates: list[dict],
    *,
    title_key: str,
    min_common: int = 2,
    jaccard_threshold: float = 0.25,
) -> tuple[int, list[dict]]:
    """Compte tous les matches d'un titre source dans les candidats.

    Différent de best_match : on collecte TOUS les matches au-dessus du
    seuil. Utile pour Google News où plusieurs médias couvrent le même
    sujet et le nombre de matches = signal de couverture.

    Retourne (count, matched_items_top_N).
    """
    from server.scoring.matcher import jaccard
    from server.scoring.normalize import token_set

    matched: list[tuple[float, dict]] = []
    for cand in candidates:
        title = cand.get(title_key) or ""
        cand_tokens = token_set(title)
        if not cand_tokens:
            continue
        common = source_tokens & cand_tokens
        score = jaccard(source_tokens, cand_tokens)
        if score >= jaccard_threshold or len(common) >= min_common:
            matched.append((score, cand))

    matched.sort(key=lambda x: x[0], reverse=True)
    return len(matched), [c for _, c in matched[:5]]


# ---------------------------------------------------------------
# Génération de la phrase rationale
# ---------------------------------------------------------------


def _rationale(
    msn_article: dict,
    discover_match: Match | None,
    trends_match: Match | None,
    wiki_match: Match | None,
    gnews_count: int,
    x_match: Match | None,
    reddit_cross: int,
    youtube_match: Match | None,
    breakdown: scoring.ScoreBreakdown,
) -> str:
    """Phrase explicative générée pour le rédac chef."""
    parts: list[str] = []

    if discover_match and breakdown.discover >= 70:
        score = discover_match.target.get("score") or 0
        parts.append(f"Forte visibilité Discover (score {score:.0f})")
    elif discover_match and breakdown.discover >= 30:
        parts.append("présent sur Google Discover")

    if trends_match and breakdown.trends >= 60:
        vol = trends_match.target.get("search_volume", 0)
        parts.append(f"pic Google Trends ({vol:,} recherches)".replace(",", " "))
    elif trends_match:
        parts.append("présent sur Google Trends")

    if wiki_match and breakdown.wiki >= 60:
        views = wiki_match.target.get("views", 0)
        parts.append(
            f"forte audience Wikipedia ({views:,} vues/jour)".replace(",", " ")
        )
    elif wiki_match:
        parts.append("présent dans le top Wikipedia")

    if gnews_count >= 5:
        parts.append(f"forte couverture médiatique ({gnews_count} médias)")
    elif gnews_count >= 2:
        parts.append(f"couvert par {gnews_count} médias")
    elif gnews_count == 1:
        parts.append("repris sur Google Actualités")

    if x_match and breakdown.x >= 60:
        parts.append("trending sur X")
    elif x_match:
        parts.append("mentionné sur X")

    if reddit_cross >= 3:
        parts.append(f"viral sur Reddit ({reddit_cross} subs FR)")
    elif reddit_cross >= 2:
        parts.append(f"présent sur {reddit_cross} subs Reddit")
    elif reddit_cross == 1:
        parts.append("repris sur Reddit FR")

    if youtube_match and breakdown.youtube >= 60:
        velocity = youtube_match.target.get("velocity_views_per_hour", 0)
        parts.append(
            f"vidéo YouTube en explosion ({velocity:,}/h vues)".replace(",", " ")
        )
    elif youtube_match:
        parts.append("présent dans YouTube Trending FR")

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
    discover_match: Match | None,
    trends_match: Match | None,
    wiki_match: Match | None,
    gnews_count: int,
    x_match: Match | None,
    reddit_cross: int,
    youtube_match: Match | None,
    msn_article: dict,
) -> list[dict[str, Any]]:
    """Construit la liste de signal pills affichée dans le front."""
    signals: list[dict[str, Any]] = []

    if discover_match:
        score = discover_match.target.get("score") or 0
        # La médiane Discoversnoop est à 0.2 — afficher "0/65" est
        # trompeur (suggère absence de signal). On distingue 3 cas :
        if score >= 10:
            value = f"{score:.0f}/65"
        elif score >= 1:
            value = f"{score:.1f}/65"
        else:
            value = "présent"
        # `source` = identifiant unique de la source utilisé côté front
        # comme sélecteur CSS `data-source="..."`. On garde un identifiant
        # par origine (discover, gnews, reddit, msn, youtube, trends, wiki, x)
        # pour pouvoir colorer chaque pastille avec les couleurs de marque
        # iconiques de la source.
        signals.append(
            {
                "source": "discover",
                "label": "discover",
                "value": value,
            }
        )

    if gnews_count > 0:
        signals.append(
            {
                "source": "gnews",
                "label": "gnews",
                "value": f"{gnews_count} média{'s' if gnews_count > 1 else ''}",
            }
        )

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

    if reddit_cross > 0:
        signals.append(
            {
                "source": "reddit",
                "label": "reddit",
                "value": (
                    f"{reddit_cross} subs"
                    if reddit_cross > 1
                    else "1 sub FR"
                ),
            }
        )

    if youtube_match:
        velocity = int(youtube_match.target.get("velocity_views_per_hour") or 0)
        signals.append(
            {
                "source": "youtube",
                "label": "youtube",
                "value": _format_volume(velocity, suffix="/h"),
            }
        )

    # Toujours indiquer MSN puisque c'est la base
    engagement = (msn_article.get("upvotes", 0) or 0) + (
        msn_article.get("comments", 0) or 0
    )
    if engagement > 0:
        signals.append(
            {
                "source": "msn",
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
    discover_match: Match | None,
    trends_match: Match | None,
    wiki_match: Match | None,
    gnews_count: int,
    x_match: Match | None,
    reddit_cross: int,
    youtube_match: Match | None,
    breakdown: scoring.ScoreBreakdown,
) -> list[dict[str, Any]]:
    """Détail par source pour l'expand row du front (bars de progression)."""
    return [
        {
            "name": "Google Discover",
            "value": (
                f"score {discover_match.target.get('score'):.1f}"
                if discover_match and discover_match.target.get("score") is not None
                else "—"
            ),
            "fill": int(breakdown.discover),
        },
        {
            "name": "Google News",
            "value": (
                f"{gnews_count} média{'s' if gnews_count > 1 else ''}"
                if gnews_count > 0
                else "—"
            ),
            "fill": int(breakdown.gnews),
        },
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
        {
            "name": "Reddit FR",
            "value": (
                f"{reddit_cross} sub{'s' if reddit_cross > 1 else ''}"
                if reddit_cross > 0
                else "—"
            ),
            "fill": int(breakdown.reddit),
        },
        {
            "name": "YouTube velocity",
            "value": (
                _format_volume(
                    int(youtube_match.target.get("velocity_views_per_hour") or 0),
                    suffix="/h",
                )
                if youtube_match
                else "—"
            ),
            "fill": int(breakdown.youtube),
        },
    ]


def _best_reddit_match(
    src_tokens: set,
    reddit_candidates: list[dict],
) -> tuple[int, int | None, list[dict]]:
    """Pour un sujet MSN, cherche les posts Reddit qui le couvrent.

    Retourne (max_cross_subs, best_rank, top_matches).
      - max_cross_subs : viralité max parmi les matches (= meilleur post,
        celui qui apparaît dans le plus de subs)
      - best_rank : meilleur rang Reddit parmi les matches (1 = très hot)
      - top_matches : 3 meilleurs posts matchés

    Si aucun match : (0, None, []).
    """
    from server.scoring.matcher import jaccard
    from server.scoring.normalize import token_set

    matched: list[tuple[float, dict]] = []
    for post in reddit_candidates:
        title = post.get("title") or ""
        cand_tokens = token_set(title)
        if not cand_tokens:
            continue
        common = src_tokens & cand_tokens
        score = jaccard(src_tokens, cand_tokens)
        # Reddit titres souvent courts/typés : seuil un peu plus lâche
        if score >= 0.25 or len(common) >= 2:
            matched.append((score, post))

    if not matched:
        return 0, None, []

    matched.sort(key=lambda x: x[0], reverse=True)
    max_cross = max(int(p.get("cross_subs_count") or 1) for _, p in matched)
    best_rank = min(int(p.get("best_rank") or 99) for _, p in matched)
    return max_cross, best_rank, [p for _, p in matched[:3]]


def _score_article(
    msn_article: dict,
    *,
    discover_candidates: list[dict],
    gt_candidates: list[dict],
    wiki_candidates: list[dict],
    gnews_candidates: list[dict],
    x_candidates: list[dict],
    reddit_candidates: list[dict],
    youtube_candidates: list[dict],
) -> dict[str, Any] | None:
    """Score un article MSN. Retourne None si titre vide."""
    title = msn_article.get("title", "")
    if not title:
        return None

    src_tokens = token_set(title)
    if not src_tokens:
        return None

    discover_match = best_match(
        src_tokens, discover_candidates, title_key="title"
    )
    trends_match = best_match(src_tokens, gt_candidates, title_key="query")
    wiki_match = best_match(src_tokens, wiki_candidates, title_key="title_display")
    x_match = best_match(src_tokens, x_candidates, title_key="query")

    # Google News : count-based. Min 2 tokens communs OU Jaccard ≥ 0.30.
    # Les stopwords FR (cf normalize.py) éliminent déjà "voici", "voila",
    # "ans", "direct" qui généraient des faux positifs.
    gnews_count, gnews_top_matches = _count_matches(
        src_tokens,
        gnews_candidates,
        title_key="title",
        min_common=2,
        jaccard_threshold=0.30,
    )

    # Reddit : virality cross-subs + best rank parmi les matches
    reddit_cross, reddit_best_rank, reddit_top = _best_reddit_match(
        src_tokens, reddit_candidates
    )

    # YouTube : best_match comme Wiki / Trends, on récupère sa velocity
    youtube_match = best_match(src_tokens, youtube_candidates, title_key="title")

    breakdown = scoring.composite_score(
        discover=(
            scoring.discover_score(discover_match.target.get("score"))
            if discover_match
            else 0.0
        ),
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
        gnews=scoring.gnews_score(gnews_count),
        msn=scoring.msn_score(msn_article),
        x=(scoring.x_score(x_match.target.get("rank")) if x_match else 0.0),
        reddit=scoring.reddit_score(reddit_cross, reddit_best_rank),
        youtube=(
            scoring.youtube_score(
                youtube_match.target.get("velocity_views_per_hour", 0)
            )
            if youtube_match
            else 0.0
        ),
    )

    return {
        "msn_article": msn_article,
        "discover_match": discover_match,
        "trends_match": trends_match,
        "wiki_match": wiki_match,
        "gnews_count": gnews_count,
        "gnews_top_matches": gnews_top_matches,
        "x_match": x_match,
        "reddit_cross": reddit_cross,
        "reddit_best_rank": reddit_best_rank,
        "reddit_top": reddit_top,
        "youtube_match": youtube_match,
        "breakdown": breakdown,
    }


def _to_sujet_dict(scored: dict[str, Any], rank: int) -> dict[str, Any]:
    """Convertit un score en sujet prêt à sérialiser pour le front."""
    article = scored["msn_article"]
    breakdown: scoring.ScoreBreakdown = scored["breakdown"]
    gnews_count = scored.get("gnews_count", 0)
    reddit_cross = scored.get("reddit_cross", 0)
    youtube_match = scored.get("youtube_match")

    rationale = _rationale(
        article,
        scored["discover_match"],
        scored["trends_match"],
        scored["wiki_match"],
        gnews_count,
        scored["x_match"],
        reddit_cross,
        youtube_match,
        breakdown,
    )

    signals = _build_signals(
        scored["discover_match"],
        scored["trends_match"],
        scored["wiki_match"],
        gnews_count,
        scored["x_match"],
        reddit_cross,
        youtube_match,
        article,
    )

    sources_detail = _build_sources_detail(
        scored["discover_match"],
        scored["trends_match"],
        scored["wiki_match"],
        gnews_count,
        scored["x_match"],
        reddit_cross,
        youtube_match,
        breakdown,
    )

    # `refs` est une liste de dicts {label, url} pour que chaque référence
    # puisse être un lien cliquable autonome côté front. Le front conserve
    # une compatibilité avec l'ancien format (string) pour les snapshots
    # antérieurs.
    refs: list[dict[str, str]] = []
    if article.get("url"):
        refs.append(
            {
                "label": f"MSN · {article.get('source', 'MSN')} — {article['title']}",
                "url": article["url"],
            }
        )

    # Métadonnées Discover pour filtrage côté front (cf click-to-filter)
    discover_match = scored["discover_match"]
    discover_category: str | None = None
    discover_entities: list[str] = []
    if discover_match:
        d_target = discover_match.target
        discover_category = (d_target.get("category") or "").strip() or None
        discover_entities = list(d_target.get("entities_list") or [])

        d_publisher = d_target.get("publisher") or "Discover"
        d_title = d_target.get("title") or ""
        d_url = d_target.get("url") or ""
        if d_title:
            refs.append(
                {
                    "label": f"Discover · {d_publisher} — {d_title}",
                    "url": d_url,
                }
            )
    # Top 3 articles Google News matchés (médias français de référence)
    for gn in (scored.get("gnews_top_matches") or [])[:3]:
        gn_source = gn.get("source") or "Google News"
        gn_title = gn.get("title") or ""
        gn_url = gn.get("url") or ""
        if gn_title:
            refs.append(
                {
                    "label": f"GNews · {gn_source} — {gn_title}",
                    "url": gn_url,
                }
            )

    # Top 2 posts Reddit matchés (lecteur de tonalité communautaire)
    for rd in (scored.get("reddit_top") or [])[:2]:
        rd_sub = rd.get("subreddit") or ""
        rd_title = rd.get("title") or ""
        # Permalink Reddit (toujours), sinon URL externe
        rd_url = rd.get("permalink") or rd.get("url") or ""
        if rd_title and rd_url:
            refs.append(
                {
                    "label": f"Reddit · r/{rd_sub} — {rd_title}",
                    "url": rd_url,
                }
            )

    # Vidéo YouTube matchée si présente (souvent un format vidéo de
    # référence pour le sujet — utile au rédac chef pour le ton)
    yt_match = scored.get("youtube_match")
    if yt_match:
        yt_target = yt_match.target
        yt_title = yt_target.get("title") or ""
        yt_url = yt_target.get("url") or ""
        yt_channel = yt_target.get("channel") or ""
        if yt_title and yt_url:
            refs.append(
                {
                    "label": f"YouTube · {yt_channel} — {yt_title}",
                    "url": yt_url,
                }
            )

    # Le scoring interne tourne sur une echelle ~/65 (max observe avec
    # les 7 sources actuelles). On rescale a /100 pour l'affichage : plus
    # naturel pour les redacteurs, et permet d'utiliser les seuils tier
    # 77/46 (= 50/30 sur l'echelle d'origine).
    rounded = int(round(breakdown.total * 100.0 / 65.0))
    rounded = max(0, min(100, rounded))
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
        # Méta pour filtrage côté front (clic sur catégorie ou entité)
        "discover_category": discover_category,
        "discover_entities": discover_entities,
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
    discover = _load("discoversnoop")
    gnews = _load("google_news")
    # Sources anticipatrices (snapshots optionnels — un premier run sans
    # ces fetchers ne doit pas casser le pipeline)
    reddit = _load_optional("reddit")
    youtube = _load_optional("youtube_trending")

    gt_candidates, x_candidates = _prepare_trends(gt, x)
    wiki_candidates = _prepare_wiki(wikimedia)
    discover_candidates = _prepare_discover(discover)
    gnews_candidates = _prepare_gnews(gnews)
    reddit_candidates = _prepare_reddit(reddit)
    youtube_candidates = _prepare_youtube(youtube)

    # Clusters Discover (catégories + entités) — vue "univers éditorial"
    discover_articles = discover.get("articles", [])
    categories_trending = clustering.cluster_by_category(discover_articles)
    entity_clusters = clustering.cluster_entities_by_cooccurrence(
        discover_articles
    )
    # Pour la vue plate, on retire les entités déjà absorbées dans un cluster
    clustered = clustering.entities_in_clusters(entity_clusters)
    entities_trending = [
        e
        for e in clustering.cluster_by_entity(discover_articles)
        if e["name"] not in clustered
    ]

    scored: list[dict[str, Any]] = []
    for article in msn.get("articles", []):
        result = _score_article(
            article,
            discover_candidates=discover_candidates,
            gt_candidates=gt_candidates,
            wiki_candidates=wiki_candidates,
            gnews_candidates=gnews_candidates,
            x_candidates=x_candidates,
            reddit_candidates=reddit_candidates,
            youtube_candidates=youtube_candidates,
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
            "discoversnoop": {
                "fetched_at": discover.get("fetched_at"),
                "count": discover.get("count"),
            },
            "google_news": {
                "fetched_at": gnews.get("fetched_at"),
                "count": gnews.get("count"),
            },
            # Reddit retire de sources_used : source desactivee en CI
            # (cf server/cli.py, commit cca660b). Les donnees historiques
            # restent disponibles dans data/reddit/*.json mais on n'expose
            # plus la source dans le dashboard pour ne pas afficher 7/8.
            "youtube_trending": {
                "fetched_at": youtube.get("fetched_at") if youtube else None,
                "count": youtube.get("count") if youtube else 0,
            },
        },
        "weights": scoring.WEIGHTS,
        "totals": {
            "candidates_scored": len(scored),
            "kept": len(sujets),
            "by_tier": counts,
        },
        "sujets": sujets,
        "categories_trending": categories_trending,
        "entity_clusters": entity_clusters,
        "entities_trending": entities_trending,
    }


def run(top_n: int = TOP_N) -> dict[str, Any]:
    payload = aggregate(top_n=top_n)
    write_snapshot("sujets", payload, today_str())
    return payload
