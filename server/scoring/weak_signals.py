"""Signaux faibles cross-source — candidats d'anticipation Discover.

Objectif : reperer les topics qui apparaissent sur >=2 sources NON-Discover
(GNews, Trends, Wikipedia, X, YouTube, MSN) mais qui ne sont PAS encore
dans Discover. Ces topics sont des candidats d'anticipation : Google
Discover les indexera potentiellement dans les 12-24h.

Algorithme :
  1. Collecter les items textuels de chaque source (titre/query) en
     gardant l'attribution source.
  2. Embed (Voyage) tous les items + tous les articles Discover.
  3. Pour chaque item non-Discover, verifier s'il match (cosine > 0.78)
     un article Discover -> si oui, on l'exclut (deja sur Discover).
  4. Cluster les items restants par cosine > 0.75 (un peu plus large
     que la dedup A1 pour grouper des formulations differentes).
  5. Garder uniquement les clusters avec >=2 sources distinctes.
  6. Composer un weak_signal par cluster : titre representant, sources,
     prediction_score (= nb_sources * sqrt(member_count)).
  7. Output trie par prediction_score decroissant.

Cout Voyage typique :
  ~1000 items + 700 Discover = 1700 embeddings, ~50 tokens/item =
  ~85k tokens/run. Tarif voyage-3 : $0.06/Mtok -> ~$0.005/run.
  Cache disque elimine les recalculs sur titres deja vus.

Si Voyage indispose, retourne [] (degrade gracieusement).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from server.scoring import embeddings

# Seuil pour considerer qu'un item non-Discover est DEJA sur Discover.
# Plus haut que semantic_dedup (0.78) car ici on veut etre conservateur :
# en cas de doute, on filtre (= on n'affiche pas un faux signal faible).
DISCOVER_MATCH_THRESHOLD = 0.75

# Seuils cluster entre items non-Discover.
# Probleme : les queries courtes (Trends, X) s'embed proches par classe
# semantique (noms de personnes, noms de sports). On utilise un seuil
# strict pour les queries courtes (< 25 chars) et plus large pour les
# vrais titres.
CLUSTER_THRESHOLD_LONG = 0.78   # >= un cote a un vrai titre (>=25 chars)
CLUSTER_THRESHOLD_SHORT = 0.88  # les deux cotes sont des queries courtes
LONG_TITLE_MIN_CHARS = 25

# Nb max de signaux faibles a remonter.
TOP_N_SIGNALS = 20

# Cap items par source pour eviter d'exploser le pool.
MAX_ITEMS_PER_SOURCE = 50

# Cap members par cluster pour eviter qu'un faux positif "noms de
# personnes" tire un cluster a 30+ items. Au-dela, on coupe.
MAX_MEMBERS_PER_CLUSTER = 8


def _collect_source_items(payloads: dict[str, dict]) -> list[dict[str, Any]]:
    """Aplatit les payloads par source en items {title, source, weight}.

    weight : poids relatif (sera utilise pour le prediction_score).
    Discover est exclu de cette collecte.
    """
    items: list[dict[str, Any]] = []

    # MSN : articles[].title
    for a in (payloads.get("msn") or {}).get("articles", [])[:MAX_ITEMS_PER_SOURCE]:
        title = (a.get("title") or "").strip()
        if title:
            items.append({"title": title, "source": "msn", "weight": 1.0})

    # Google News : articles[].title
    for a in (payloads.get("gnews") or {}).get("articles", [])[:MAX_ITEMS_PER_SOURCE]:
        title = (a.get("title") or "").strip()
        if title:
            items.append({"title": title, "source": "gnews", "weight": 1.0})

    # Google Trends : windows.current.trends[].query (avec search_volume
    # comme weight)
    gt = (payloads.get("trends") or {}).get("windows", {}).get("current", {})
    for t in (gt.get("trends") or [])[:MAX_ITEMS_PER_SOURCE]:
        q = (t.get("query") or "").strip()
        if q:
            vol = t.get("search_volume") or 0
            items.append({
                "title": q,
                "source": "trends",
                "weight": 1.0 + min(2.0, (vol / 100_000) if vol else 0),
            })

    # Wikipedia : articles[].title_display (ou article)
    for a in (payloads.get("wiki") or {}).get("articles", [])[:MAX_ITEMS_PER_SOURCE]:
        title = (a.get("title_display") or a.get("article") or "").strip()
        if title:
            items.append({"title": title, "source": "wiki", "weight": 1.0})

    # X Trends : trends[].query
    for t in (payloads.get("x") or {}).get("trends", [])[:MAX_ITEMS_PER_SOURCE]:
        q = (t.get("query") or "").strip()
        if q:
            items.append({"title": q, "source": "x", "weight": 0.8})

    # YouTube : videos[].title (deja filtrees a 50 dans le fetcher v2)
    for v in (payloads.get("youtube") or {}).get("videos", [])[:MAX_ITEMS_PER_SOURCE]:
        title = (v.get("title") or "").strip()
        if title:
            # Bonus si la chaine est dans la whitelist editoriale (V2)
            weight = 1.5 if v.get("is_editorial") else 0.9
            items.append({"title": title, "source": "youtube", "weight": weight})

    # TikTok : items[].title (description) — signal "viralite jeune"
    # 12-24h en amont de Discover.
    for v in (payloads.get("tiktok") or {}).get("items", [])[:MAX_ITEMS_PER_SOURCE]:
        title = (v.get("title") or "").strip()
        if title:
            items.append({"title": title, "source": "tiktok", "weight": 1.0})

    return items


def _collect_discover_items(payloads: dict[str, dict]) -> list[str]:
    """Liste plate des titres Discover (pour exclusion)."""
    discover = payloads.get("discover") or {}
    titles: list[str] = []
    for a in (discover.get("articles") or []):
        title = (a.get("title") or "").strip()
        if title:
            titles.append(title)
    return titles


def detect(payloads: dict[str, dict]) -> list[dict[str, Any]]:
    """Pipeline principal. Retourne la liste des signaux faibles tries.

    Args:
        payloads : dict avec les payloads bruts des 7 sources, indexes
                   par leur cle frontend : msn, gnews, trends, wiki,
                   x, youtube, discover.

    Returns:
        Liste de dicts : {
            "topic": str (titre representant),
            "sources": list[str] (sources distinctes),
            "members": list[{title, source}],
            "member_count": int,
            "prediction_score": float,
        }
    """
    non_discover = _collect_source_items(payloads)
    discover_titles = _collect_discover_items(payloads)

    if not non_discover:
        return []

    # 1. Embed tous les items (non-Discover + Discover) en un seul batch
    #    pour amortir le call API. Le cache disque elimine les recalculs.
    all_texts = [it["title"] for it in non_discover] + discover_titles

    try:
        vectors, backend = embeddings.embed_batch(all_texts)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[weak_signals] embeddings KO ({type(exc).__name__}: {exc}) — "
            "skip detection"
        )
        return []

    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    matrix_n = matrix / norms

    n_non_disc = len(non_discover)
    non_disc_vecs = matrix_n[:n_non_disc]
    disc_vecs = matrix_n[n_non_disc:]

    # 2. Filtre les items non-Discover qui matchent un article Discover
    #    (= deja sur Discover, pas un signal faible).
    if len(disc_vecs):
        # cosine entre chaque non_disc et chaque disc, on prend le max
        sims_to_disc = non_disc_vecs @ disc_vecs.T  # (n_non_disc, n_disc)
        max_sims = sims_to_disc.max(axis=1)
    else:
        max_sims = np.zeros(n_non_disc, dtype=np.float32)

    candidates_idx = [
        i for i in range(n_non_disc)
        if max_sims[i] < DISCOVER_MATCH_THRESHOLD
    ]

    if not candidates_idx:
        print("[weak_signals] tous les items sont deja matches sur Discover")
        return []

    # 3. Cluster les candidats entre eux (greedy agglomeratif, ordre =
    #    poids decroissant pour que le representant soit toujours le
    #    plus saillant).
    candidates_idx.sort(key=lambda i: non_discover[i]["weight"], reverse=True)

    cluster_reps: list[int] = []
    cluster_members: dict[int, list[int]] = {}

    for i in candidates_idx:
        joined = False
        title_i = non_discover[i]["title"]
        for rep in cluster_reps:
            # Seuil variable selon la longueur des titres : queries
            # courtes -> seuil strict (0.88), vrais titres -> 0.78.
            title_rep = non_discover[rep]["title"]
            both_short = (
                len(title_i) < LONG_TITLE_MIN_CHARS
                and len(title_rep) < LONG_TITLE_MIN_CHARS
            )
            threshold = (
                CLUSTER_THRESHOLD_SHORT if both_short
                else CLUSTER_THRESHOLD_LONG
            )
            sim = float(non_disc_vecs[i] @ non_disc_vecs[rep])
            if sim >= threshold:
                # Cap members par cluster pour eviter les faux positifs
                # qui aspirent toute une categorie semantique.
                if len(cluster_members[rep]) < MAX_MEMBERS_PER_CLUSTER:
                    cluster_members[rep].append(i)
                joined = True
                break
        if not joined:
            cluster_reps.append(i)
            cluster_members[i] = [i]

    # 4. Pour chaque cluster, calculer sources distinctes + prediction_score.
    weak_signals: list[dict[str, Any]] = []
    for rep in cluster_reps:
        members = cluster_members[rep]
        # Sources distinctes : un cluster avec 5 items GNews + 0 ailleurs
        # n'est PAS un signal cross-source. Il faut >= 2 sources.
        sources_set = {non_discover[m]["source"] for m in members}
        if len(sources_set) < 2:
            continue

        rep_item = non_discover[rep]
        members_meta = [
            {"title": non_discover[m]["title"], "source": non_discover[m]["source"]}
            for m in members
        ]

        # prediction_score : recompense la diversite de sources +
        # le volume total + la qualite editoriale (poids des items).
        total_weight = sum(non_discover[m]["weight"] for m in members)
        prediction_score = round(
            len(sources_set) * 10 + total_weight * 1.5 + len(members) * 0.5,
            2,
        )

        weak_signals.append({
            "topic": rep_item["title"],
            "sources": sorted(sources_set),
            "members": members_meta,
            "member_count": len(members),
            "prediction_score": prediction_score,
        })

    # 5. Tri + cap
    weak_signals.sort(key=lambda w: w["prediction_score"], reverse=True)
    weak_signals = weak_signals[:TOP_N_SIGNALS]

    if weak_signals:
        n_clusters = len([1 for _ in cluster_reps])
        print(
            f"[weak_signals] {len(weak_signals)} signaux faibles detectes "
            f"(sur {n_clusters} clusters candidats, "
            f"{len(candidates_idx)} items non-Discover, backend={backend})"
        )

    return weak_signals
