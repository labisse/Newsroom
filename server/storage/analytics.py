"""Vues analytiques sur la base time-series.

Requêtes SQL qui transforment les snapshots bruts (4 tables) en
indicateurs exploitables côté front :

  1. Topics qui montent : delta articles_count par entity/cluster/category
     sur les dernières 24h (= candidats anticipation Discover)
  2. Sujets persistants : titres qui apparaissent dans plusieurs snapshots
     consécutifs (= signal éditorial durable vs effet d'actualité court)
  3. Catégories qui s'activent : variation items_count par
     (catégorie canonique × source) sur 24h
  4. Pulse sources : courbe de count par source sur 7 jours
     (santé pipeline + détection de hausse macro)

Toutes les requêtes sont tolérantes au faible volume initial : si on a
qu'un seul snapshot, delta sera NULL/0 mais on affiche quand même les
counts du jour.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from server.storage.timeseries import _connect, is_enabled


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


# ---------------------------------------------------------------
# 1. Topics qui montent
# ---------------------------------------------------------------


TOPICS_MOMENTUM_SQL = """
WITH latest AS (
    -- Pour chaque (topic_kind, topic_name) : le snapshot le plus récent
    SELECT DISTINCT ON (topic_kind, topic_name)
        topic_kind, topic_name, topic_label,
        articles_count AS current_count,
        snapshot_at AS latest_at,
        sample_articles
    FROM topic_pulse
    ORDER BY topic_kind, topic_name, snapshot_at DESC
),
previous AS (
    -- Pour chaque (topic_kind, topic_name) : le snapshot le plus récent
    -- d'il y a AU MOINS `window_hours` heures
    SELECT DISTINCT ON (topic_kind, topic_name)
        topic_kind, topic_name,
        articles_count AS prev_count,
        snapshot_at AS prev_at
    FROM topic_pulse
    WHERE snapshot_at <= NOW() - (%s || ' hours')::interval
    ORDER BY topic_kind, topic_name, snapshot_at DESC
)
SELECT
    l.topic_kind, l.topic_name, l.topic_label,
    l.current_count,
    COALESCE(p.prev_count, 0) AS prev_count,
    l.current_count - COALESCE(p.prev_count, 0) AS delta,
    CASE
        WHEN COALESCE(p.prev_count, 0) > 0
            THEN ROUND(100.0 * (l.current_count - p.prev_count) / p.prev_count)
        ELSE NULL
    END AS pct_change,
    l.latest_at,
    p.prev_at,
    l.sample_articles
FROM latest l
LEFT JOIN previous p USING (topic_kind, topic_name)
-- Filtre bruit : topics trop faibles
WHERE l.current_count >= %s
ORDER BY
    -- D'abord les vraies montées (delta > 0), puis les stables
    CASE WHEN l.current_count - COALESCE(p.prev_count, 0) > 0 THEN 0 ELSE 1 END,
    (l.current_count - COALESCE(p.prev_count, 0)) DESC,
    l.current_count DESC
LIMIT %s;
"""


def topics_momentum(
    window_hours: int = 24,
    min_count: int = 3,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Top topics par variation articles_count dans la fenêtre window_hours.

    Retourne entités + clusters + catégories Discover triés par delta
    décroissant. Topics avec current_count < min_count exclus (bruit).
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(TOPICS_MOMENTUM_SQL, (window_hours, min_count, limit))
            rows = cur.fetchall()
    return [
        {
            "topic_kind": kind,
            "topic_name": name,
            "topic_label": label,
            "current_count": int(curr),
            "prev_count": int(prev),
            "delta": int(delta),
            "pct_change": int(pct) if pct is not None else None,
            "latest_at": _iso(latest),
            "prev_at": _iso(prev_at),
            "sample_articles": sample or [],
        }
        for kind, name, label, curr, prev, delta, pct, latest, prev_at, sample in rows
    ]


# ---------------------------------------------------------------
# 2. Sujets persistants (un même sujet qui revient dans plusieurs snapshots)
# ---------------------------------------------------------------


SUJETS_PERSISTENCE_SQL = """
SELECT
    title_hash,
    MIN(title) AS title,
    COUNT(*) AS appearances,
    MIN(snapshot_at) AS first_seen,
    MAX(snapshot_at) AS last_seen,
    MAX(score) AS max_score,
    -- Premier score (chronologiquement)
    (ARRAY_AGG(score ORDER BY snapshot_at ASC))[1] AS first_score,
    -- Dernier score
    (ARRAY_AGG(score ORDER BY snapshot_at DESC))[1] AS last_score,
    -- Catégorie la plus fréquente
    MODE() WITHIN GROUP (ORDER BY discover_category) AS most_common_category,
    -- URL MSN du dernier snapshot
    (ARRAY_AGG(msn_url ORDER BY snapshot_at DESC))[1] AS latest_msn_url,
    (ARRAY_AGG(msn_source_name ORDER BY snapshot_at DESC))[1] AS latest_source
FROM sujets_snapshots
WHERE snapshot_at > NOW() - (%s || ' days')::interval
GROUP BY title_hash
HAVING COUNT(*) >= %s
ORDER BY
    -- Sujets persistants ET en hausse de score = très intéressants
    COUNT(*) DESC,
    MAX(score) DESC
LIMIT %s;
"""


def sujets_persistence(
    window_days: int = 3,
    min_appearances: int = 2,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Sujets globaux qui apparaissent dans plusieurs snapshots consécutifs.

    Un sujet qui revient plusieurs fois = signal éditorial qui dure, vs
    sujet ponctuel (1 seul snapshot). Important pour distinguer le bruit
    de la tendance.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                SUJETS_PERSISTENCE_SQL,
                (window_days, min_appearances, limit),
            )
            rows = cur.fetchall()
    return [
        {
            "title_hash": title_hash,
            "title": title,
            "appearances": int(appearances),
            "first_seen": _iso(first_seen),
            "last_seen": _iso(last_seen),
            "max_score": int(max_score) if max_score is not None else 0,
            "first_score": int(first_score) if first_score is not None else 0,
            "last_score": int(last_score) if last_score is not None else 0,
            "score_delta": (
                int(last_score) - int(first_score)
                if last_score is not None and first_score is not None
                else 0
            ),
            "category": cat,
            "msn_url": url,
            "source": source,
        }
        for (
            title_hash, title, appearances, first_seen, last_seen,
            max_score, first_score, last_score, cat, url, source,
        ) in rows
    ]


# ---------------------------------------------------------------
# 3. Catégories qui s'activent (heatmap cat × source sur 24h)
# ---------------------------------------------------------------


CATEGORY_MOMENTUM_SQL = """
WITH latest AS (
    SELECT DISTINCT ON (category, source)
        category, source,
        items_count AS current_count,
        snapshot_at AS latest_at
    FROM category_pulse
    ORDER BY category, source, snapshot_at DESC
),
previous AS (
    SELECT DISTINCT ON (category, source)
        category, source,
        items_count AS prev_count
    FROM category_pulse
    WHERE snapshot_at <= NOW() - (%s || ' hours')::interval
    ORDER BY category, source, snapshot_at DESC
)
SELECT
    l.category, l.source,
    l.current_count,
    COALESCE(p.prev_count, 0) AS prev_count,
    l.current_count - COALESCE(p.prev_count, 0) AS delta,
    l.latest_at
FROM latest l
LEFT JOIN previous p USING (category, source)
ORDER BY l.category, l.source;
"""


def category_momentum(window_hours: int = 24) -> list[dict[str, Any]]:
    """Variation items_count par (catégorie × source) sur window_hours.

    Permet d'afficher une heatmap 10 cats × 6 sources avec les deltas.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(CATEGORY_MOMENTUM_SQL, (window_hours,))
            rows = cur.fetchall()
    return [
        {
            "category": cat,
            "source": src,
            "current_count": int(curr),
            "prev_count": int(prev),
            "delta": int(delta),
            "latest_at": _iso(latest),
        }
        for cat, src, curr, prev, delta, latest in rows
    ]


# ---------------------------------------------------------------
# 4. Pulse sources : série temporelle count par source sur 7j
# ---------------------------------------------------------------


SOURCE_TIMELINE_SQL = """
SELECT source, snapshot_at, count
FROM source_pulse
WHERE snapshot_at > NOW() - INTERVAL '7 days'
ORDER BY source, snapshot_at ASC;
"""


def source_timeline() -> dict[str, list[dict[str, Any]]]:
    """Time series count par source sur 7 jours.

    Retourne {source_key: [{snapshot_at, count}, ...]} pour rendre des
    sparklines/courbes côté front.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SOURCE_TIMELINE_SQL)
            rows = cur.fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for src, snap_at, count in rows:
        out.setdefault(src, []).append(
            {"at": _iso(snap_at), "count": int(count)}
        )
    return out


# ---------------------------------------------------------------
# Bundle complet pour export front
# ---------------------------------------------------------------


def build_evolution_payload() -> dict[str, Any]:
    """Bundle des 4 vues pour export en JSON consommable par le front."""
    if not is_enabled():
        return {
            "available": False,
            "reason": "DATABASE_URL non définie",
        }

    return {
        "available": True,
        "generated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "topics_24h": topics_momentum(window_hours=24, min_count=3, limit=40),
        "topics_48h": topics_momentum(window_hours=48, min_count=3, limit=40),
        "sujets_persistance": sujets_persistence(
            window_days=3, min_appearances=2, limit=30
        ),
        "category_momentum_24h": category_momentum(window_hours=24),
        "source_timeline_7d": source_timeline(),
    }
