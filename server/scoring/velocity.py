"""Velocity scoring — annotation des sujets avec leur trajectoire 24h.

Pour chaque sujet de `data/sujets/latest.json`, on requete la BDD
time-series (`sujets_snapshots`) pour retrouver le score historique
6h et 24h plus tot. On en deduit :

  - velocity_6h  : score_now - score_6h_ago   (points/6h)
  - velocity_24h : score_now - score_24h_ago  (points/24h)
  - trend        : "rising" / "stable" / "falling" / "new"

Si la BDD est indisponible (DATABASE_URL non definie), les champs sont
None et le front affiche un placeholder neutre.

Ce module tourne en post-traitement de `aggregator.run()`. Il ne touche
pas au scoring : il enrichit juste le sujet a posteriori.
"""

from __future__ import annotations

from typing import Any

from server.storage.timeseries import _connect, is_enabled

# Seuils velocity (points). Calibres sur l'echelle d'affichage post-x1.2.
RISING_THRESHOLD = 5  # >= +5 points en 6h = "monte vite"
FALLING_THRESHOLD = -5  # <= -5 points en 6h = "redescend"


VELOCITY_LOOKUP_SQL = """
SELECT
    title_hash,
    score AS prev_score,
    snapshot_at
FROM sujets_snapshots
WHERE title_hash = ANY(%s)
  AND snapshot_at <= NOW() - (%s || ' hours')::interval
ORDER BY title_hash, snapshot_at DESC
"""


def _trend_label(velocity_6h: int | None) -> str:
    """Convertit la velocity_6h en label trend pour le front."""
    if velocity_6h is None:
        return "new"  # pas d'historique = sujet nouveau
    if velocity_6h >= RISING_THRESHOLD:
        return "rising"
    if velocity_6h <= FALLING_THRESHOLD:
        return "falling"
    return "stable"


def _fetch_prev_scores(
    title_hashes: list[str], hours_ago: int
) -> dict[str, int]:
    """Pour chaque title_hash, retrouve le score d'il y a `hours_ago` heures.

    On prend le snapshot le plus recent ANTERIEUR a `hours_ago` heures.
    Retourne un dict {title_hash: prev_score}.
    """
    if not title_hashes:
        return {}

    out: dict[str, int] = {}
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(VELOCITY_LOOKUP_SQL, (title_hashes, hours_ago))
            # ORDER BY title_hash, snapshot_at DESC : on garde la 1ere
            # occurrence (= la plus recente avant le seuil temporel).
            seen: set[str] = set()
            for row in cur.fetchall():
                th = row[0]
                if th in seen:
                    continue
                seen.add(th)
                out[th] = int(row[1])
    return out


def annotate(payload: dict[str, Any]) -> dict[str, Any]:
    """Enrichit chaque sujet du payload avec velocity_6h, velocity_24h, trend.

    Retourne le meme payload (mute la liste sujets).
    Si la BDD est indisponible, met les champs a None et trend="new".
    """
    sujets = payload.get("sujets", [])
    if not sujets:
        return payload

    if not is_enabled():
        for s in sujets:
            s["velocity_6h"] = None
            s["velocity_24h"] = None
            s["trend"] = "new"
        return payload

    # Le title_hash n'est pas inclus dans le payload front. On le
    # recalcule a partir du titre via le meme algo que timeseries.py.
    from server.storage.timeseries import _hash_title

    hashes = [_hash_title(s["title"]) for s in sujets]

    try:
        prev_6h = _fetch_prev_scores(hashes, hours_ago=6)
        prev_24h = _fetch_prev_scores(hashes, hours_ago=24)
    except Exception as exc:  # noqa: BLE001
        # BDD inaccessible (timeout reseau, secrets manquants...) :
        # on degrade en mode "new" plutot que de planter le pipeline.
        print(f"[velocity] BDD inaccessible : {type(exc).__name__}: {exc}")
        for s in sujets:
            s["velocity_6h"] = None
            s["velocity_24h"] = None
            s["trend"] = "new"
        return payload

    for s, th in zip(sujets, hashes):
        current = int(s.get("score", 0))
        p6 = prev_6h.get(th)
        p24 = prev_24h.get(th)
        v6 = (current - p6) if p6 is not None else None
        v24 = (current - p24) if p24 is not None else None
        s["velocity_6h"] = v6
        s["velocity_24h"] = v24
        s["trend"] = _trend_label(v6)

    return payload
