"""PostgreSQL time-series storage pour l'évolution des sujets/topics.

Architecture :
  - sujets_snapshots  : flux global (30 sujets par snapshot, ~120/jour à 4 runs)
  - topic_pulse       : entités/clusters/catégories Discover (1 ligne par item)
  - category_pulse    : 10 catégories canoniques × 6 sources (60 lignes/snapshot)
  - source_pulse      : counts bruts par source (8 lignes/snapshot)

Tout est *idempotent* : `init_schema()` peut être rejoué sans risque,
les insertions sont indépendantes (pas de UPSERT) car on garde toutes
les versions pour le time-series.

Le storage est *optionnel* : si DATABASE_URL est vide ou psycopg absent,
les fonctions retournent 0 silencieusement et le reste du pipeline
continue. Permet le développement local sans DB.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

# psycopg3 (psycopg[binary]) — modern API, sync mode pour matcher le reste
# du pipeline qui est synchrone.
try:
    import psycopg
    HAS_PSYCOPG = True
except ImportError:
    psycopg = None  # type: ignore
    HAS_PSYCOPG = False

from server.config import settings


# ---------------------------------------------------------------
# Activation + connexion
# ---------------------------------------------------------------


def is_enabled() -> bool:
    """True si on peut écrire en DB (driver + URL présents)."""
    return HAS_PSYCOPG and bool(settings.database_url)


def _require_enabled() -> None:
    if not HAS_PSYCOPG:
        raise RuntimeError(
            "psycopg non installé. Lance : pip install 'psycopg[binary]'"
        )
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL non définie. Configure-la dans .env "
            "(format: postgresql://user:pw@host:port/db?sslmode=require)"
        )


def _connect():
    _require_enabled()
    # autocommit=False : on commit explicitement après chaque batch
    return psycopg.connect(settings.database_url)


# ---------------------------------------------------------------
# Schéma — idempotent, joué au premier `db-init`
# ---------------------------------------------------------------


SCHEMA_SQL = """
-- Flux global de sujets : 30 sujets × 4 runs/jour
CREATE TABLE IF NOT EXISTS sujets_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL,
    sujet_id VARCHAR(20),
    rank INT NOT NULL,
    title TEXT NOT NULL,
    -- Hash SHA-256 du titre normalisé : permet de tracker un même sujet
    -- au fil des snapshots (apparition, persistance, score evolution).
    title_hash VARCHAR(64) NOT NULL,
    score INT NOT NULL,
    tier VARCHAR(10),
    theme VARCHAR(120),
    discover_category VARCHAR(200),
    discover_entities JSONB,
    score_breakdown JSONB,
    raw_signals JSONB,
    msn_url TEXT,
    msn_source_name VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sujets_snapshot_at
    ON sujets_snapshots (snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_sujets_title_hash
    ON sujets_snapshots (title_hash, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_sujets_category
    ON sujets_snapshots (discover_category, snapshot_at DESC);


-- Topics : chaque entité/cluster/catégorie Discover à chaque snapshot.
-- Pour anticipation : delta articles_count entre snapshots successifs
-- sur un même topic_name = "vitesse de montée".
CREATE TABLE IF NOT EXISTS topic_pulse (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL,
    topic_kind VARCHAR(20) NOT NULL,  -- 'entity' | 'cluster' | 'category'
    topic_name VARCHAR(300) NOT NULL,
    topic_label VARCHAR(300),
    articles_count INT NOT NULL,
    total_score NUMERIC,
    avg_score NUMERIC,
    members JSONB,           -- pour clusters : entités membres
    sample_articles JSONB,   -- top 3-5 articles pour retrouver le contexte
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_topic_pulse_snapshot_at
    ON topic_pulse (snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_topic_pulse_name_time
    ON topic_pulse (topic_name, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_topic_pulse_kind_time
    ON topic_pulse (topic_kind, snapshot_at DESC);


-- Catégories canoniques cross-source (10 cats × ~6 sources = 60/snapshot)
-- Pour visualiser quelle catégorie s'active sur quelle plateforme.
CREATE TABLE IF NOT EXISTS category_pulse (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL,
    category VARCHAR(50) NOT NULL,
    source VARCHAR(30) NOT NULL,
    items_count INT NOT NULL,
    top_items JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_category_pulse_snapshot_at
    ON category_pulse (snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_category_pulse_cat_time
    ON category_pulse (category, snapshot_at DESC);


-- Pulse brut par source (debug/santé pipeline + analyse macro).
CREATE TABLE IF NOT EXISTS source_pulse (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL,
    source VARCHAR(30) NOT NULL,
    count INT NOT NULL,
    fetched_at TIMESTAMPTZ,
    failures JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_source_pulse_snapshot_at
    ON source_pulse (snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_pulse_src_time
    ON source_pulse (source, snapshot_at DESC);
"""


def init_schema() -> None:
    """Crée les 4 tables + index. Idempotent."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def _hash_title(title: str) -> str:
    """SHA-256 du titre normalisé (lowercase, ponctuation collapsée)."""
    norm = re.sub(r"[^\w\s]", " ", (title or "").lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _to_jsonb(value: Any) -> str:
    """Sérialise en JSON pour insertion JSONB."""
    return json.dumps(value, ensure_ascii=False) if value is not None else "null"


# ---------------------------------------------------------------
# Snapshot des sujets globaux
# ---------------------------------------------------------------


def snapshot_sujets(sujets_payload: dict[str, Any]) -> int:
    """Insère un snapshot de tous les sujets du flux global.

    Retourne le nombre de lignes insérées.
    """
    sujets = sujets_payload.get("sujets") or []
    snapshot_at = (
        _parse_iso(sujets_payload.get("generated_at"))
        or datetime.now(timezone.utc)
    )

    rows = []
    for s in sujets:
        title = s.get("title", "")
        rows.append(
            (
                snapshot_at,
                s.get("id"),
                int(s.get("rank", 0)),
                title,
                _hash_title(title),
                int(s.get("score", 0)),
                s.get("tier"),
                s.get("theme"),
                s.get("discover_category"),
                _to_jsonb(s.get("discover_entities") or []),
                _to_jsonb(s.get("score_breakdown") or {}),
                _to_jsonb(s.get("signals") or []),
                s.get("msn_url"),
                s.get("msn_source_name"),
            )
        )

    if not rows:
        return 0

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO sujets_snapshots
                  (snapshot_at, sujet_id, rank, title, title_hash, score, tier,
                   theme, discover_category, discover_entities, score_breakdown,
                   raw_signals, msn_url, msn_source_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
    return len(rows)


# ---------------------------------------------------------------
# Snapshot des topics (entités + clusters + catégories Discover)
# ---------------------------------------------------------------


def snapshot_topics(sujets_payload: dict[str, Any]) -> int:
    """Insère un snapshot des entités plates + clusters + catégories Discover.

    Source : sujets_payload['entities_trending'/'entity_clusters'/'categories_trending'].
    Retourne le nombre total de lignes insérées.
    """
    snapshot_at = (
        _parse_iso(sujets_payload.get("generated_at"))
        or datetime.now(timezone.utc)
    )

    rows: list[tuple] = []

    # Entités plates
    for e in sujets_payload.get("entities_trending") or []:
        name = (e.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            (
                snapshot_at, "entity", name, name,
                int(e.get("articles_count", 0) or 0),
                e.get("total_score"),
                e.get("avg_score"),
                None,
                _to_jsonb(e.get("top_articles") or []),
            )
        )

    # Clusters d'entités (co-occurrence)
    for c in sujets_payload.get("entity_clusters") or []:
        label = (c.get("label") or "").strip()
        if not label:
            continue
        rows.append(
            (
                snapshot_at, "cluster", label, label,
                int(c.get("articles_count", 0) or 0),
                c.get("total_score"),
                c.get("avg_score"),
                _to_jsonb(c.get("members") or []),
                _to_jsonb(c.get("top_articles") or []),
            )
        )

    # Catégories Discover (taxonomie Google /News, /Sports, etc.)
    for cat in sujets_payload.get("categories_trending") or []:
        key = (cat.get("key") or "").strip()
        if not key:
            continue
        rows.append(
            (
                snapshot_at, "category", key, cat.get("label") or key,
                int(cat.get("articles_count", 0) or 0),
                cat.get("total_score"),
                cat.get("avg_score"),
                None,
                _to_jsonb(cat.get("top_articles") or []),
            )
        )

    if not rows:
        return 0

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO topic_pulse
                  (snapshot_at, topic_kind, topic_name, topic_label,
                   articles_count, total_score, avg_score, members, sample_articles)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
    return len(rows)


# ---------------------------------------------------------------
# Snapshot pulse par source
# ---------------------------------------------------------------


def snapshot_sources(sources_used: dict[str, Any]) -> int:
    """Insère un snapshot des counts bruts par source.

    Format attendu :
      sources_used = sujets_payload['sources_used'] = {
        'msn': {'fetched_at': '...', 'count': 100},
        'reddit': {'fetched_at': '...', 'count': 251},
        ...
      }
    """
    snapshot_at = datetime.now(timezone.utc)

    rows = []
    for src, meta in (sources_used or {}).items():
        if not isinstance(meta, dict):
            continue
        fetched_at = _parse_iso(meta.get("fetched_at"))
        metadata = {
            k: v
            for k, v in meta.items()
            if k not in ("count", "fetched_at", "failures")
        }
        rows.append(
            (
                snapshot_at,
                src,
                int(meta.get("count", 0) or 0),
                fetched_at,
                _to_jsonb(meta.get("failures") or []),
                _to_jsonb(metadata),
            )
        )

    if not rows:
        return 0

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO source_pulse
                  (snapshot_at, source, count, fetched_at, failures, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
    return len(rows)


# ---------------------------------------------------------------
# Snapshot catégories canoniques (10 catégories × 6 sources)
# ---------------------------------------------------------------


# Mapping canonique pour les snapshots backend (cohérent avec
# scripts/categories.js côté front). Ces 10 catégories sont notre
# taxonomie produit, indépendamment des taxonomies natives des sources.
CANONICAL_CATEGORIES = [
    "politique",
    "international",
    "economie",
    "tech",
    "sport",
    "people",
    "science",
    "sante",
    "societe",
    "lifestyle",
]


def _classify_discover(category: str | None) -> str | None:
    c = category or ""
    if c.startswith("/News/Politics"):
        return "politique"
    if c.startswith("/News/World News"):
        return "international"
    if c.startswith("/News/Business News"):
        return "economie"
    if c.startswith("/News/Sports News"):
        return "sport"
    if c.startswith("/Law & Government"):
        return "politique"
    if c.startswith("/Sports"):
        return "sport"
    if c.startswith("/Arts & Entertainment"):
        return "people"
    if c.startswith("/Health"):
        return "sante"
    if c.startswith("/Beauty & Fitness"):
        return "sante"
    if c.startswith("/Science"):
        return "science"
    if c.startswith(("/Computers", "/Internet")):
        return "tech"
    if c.startswith(("/Finance", "/Business & Industrial")):
        return "economie"
    if c.startswith(
        ("/Food", "/Travel", "/Home", "/Autos", "/Pets", "/Hobbies")
    ):
        return "lifestyle"
    if c.startswith(("/People & Society", "/Sensitive Subjects")):
        return "societe"
    if c.startswith("/News"):
        return "societe"
    return None


def _classify_gnews(category: str | None) -> str | None:
    c = (category or "").lower()
    return {
        "politique": "politique",
        "international": "international",
        "economie": "economie",
        "technologie": "tech",
        "sports": "sport",
        "divertissement": "people",
        "science": "science",
        "sante": "sante",
        "france": "societe",
    }.get(c)


def _classify_msn(category: str | None) -> str | None:
    c = (category or "").lower()
    if "politique" in c:
        return "politique"
    if "sport" in c:
        return "sport"
    if "divertissement" in c:
        return "people"
    if "lifestyle" in c or "style" in c:
        return "lifestyle"
    if "finance" in c or c.startswith("eco"):
        return "economie"
    if "tech" in c or "numer" in c:
        return "tech"
    if "sante" in c:
        return "sante"
    if "science" in c:
        return "science"
    if "monde" in c or "inter" in c:
        return "international"
    if c == "actualite":
        return "societe"
    return None


REDDIT_SUB_MAP = {
    "france": "societe",
    "actualite": "societe",
    "AskFrance": "societe",
    "francepolitique": "politique",
    "Politique": "politique",
    "europe": "international",
    "sciences": "science",
    "Histoire": "science",
    "technologie": "tech",
    "jeuxvideo": "people",
    "cinema_francais": "people",
    "musique": "people",
    "musiquefrancaise": "people",
    "Cuisine": "lifestyle",
    "cuisine": "lifestyle",
    "sport_FR": "sport",
}


YOUTUBE_CAT_MAP = {
    "Actualités & politique": "politique",
    "Sport": "sport",
    "Sciences & tech": "tech",
    "Films & animation": "people",
    "Musique": "people",
    "Divertissement": "people",
    "Comédie": "people",
    "Vlogs": "lifestyle",
    "Conseils & style": "lifestyle",
    "Éducation": "science",
    "Jeux vidéo": "people",
}


def _load_source_snapshot(source: str) -> dict[str, Any] | None:
    """Charge data/{source}/latest.json. None si absent."""
    from server.config import DATA_DIR

    path = DATA_DIR / source / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def snapshot_categories() -> int:
    """Calcule un snapshot par (catégorie canonique × source) et l'insère.

    Lit les snapshots locaux (data/<source>/latest.json), classifie chaque
    item, agrège les counts. Une ligne par couple (cat, source) avec un
    items_count = 0 si la combo n'a aucun item (utile pour les graphes
    de séries qui doivent avoir des points même à zéro).

    Returns total rows inserted.
    """
    snapshot_at = datetime.now(timezone.utc)

    # Init buckets : {cat: {source: [items]}}
    buckets: dict[str, dict[str, list[dict]]] = {
        cat: {src: [] for src in ("discover", "gnews", "msn", "reddit", "youtube")}
        for cat in CANONICAL_CATEGORIES
    }

    # Discover
    discover = _load_source_snapshot("discoversnoop")
    if discover:
        for a in discover.get("articles") or []:
            cat = _classify_discover(a.get("category"))
            if cat:
                buckets[cat]["discover"].append(a)

    # Google News
    gnews = _load_source_snapshot("google_news")
    if gnews:
        for a in gnews.get("articles") or []:
            cat = _classify_gnews(a.get("category"))
            if cat:
                buckets[cat]["gnews"].append(a)

    # MSN
    msn = _load_source_snapshot("msn")
    if msn:
        for a in msn.get("articles") or []:
            cat = _classify_msn(a.get("category"))
            if cat:
                buckets[cat]["msn"].append(a)

    # Reddit
    reddit = _load_source_snapshot("reddit")
    if reddit:
        for p in reddit.get("posts") or []:
            cat = REDDIT_SUB_MAP.get(p.get("subreddit", ""))
            if cat:
                buckets[cat]["reddit"].append(p)

    # YouTube
    youtube = _load_source_snapshot("youtube_trending")
    if youtube:
        for v in youtube.get("videos") or []:
            cat = YOUTUBE_CAT_MAP.get(v.get("category_label", ""))
            if cat:
                buckets[cat]["youtube"].append(v)

    # Sérialise : top 5 items par bucket (titres + URLs pour le contexte)
    rows = []
    for cat, sources in buckets.items():
        for src, items in sources.items():
            top_items = [
                {
                    "title": it.get("title") or it.get("query") or "",
                    "url": it.get("url") or it.get("permalink") or "",
                    "publisher": (
                        it.get("publisher")
                        or it.get("source")
                        or it.get("channel")
                        or it.get("subreddit")
                        or ""
                    ),
                }
                for it in items[:5]
            ]
            rows.append(
                (
                    snapshot_at,
                    cat,
                    src,
                    len(items),
                    _to_jsonb(top_items),
                )
            )

    if not rows:
        return 0

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO category_pulse
                  (snapshot_at, category, source, items_count, top_items)
                VALUES (%s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
    return len(rows)


# ---------------------------------------------------------------
# Pipeline complet
# ---------------------------------------------------------------


def snapshot_all() -> dict[str, int]:
    """Pipeline complet : 4 snapshots dans les 4 tables.

    Lit data/sujets/latest.json (déjà généré par `python -m server.cli score`)
    et les snapshots des sources brutes. Retourne un dict
    {table: rows_inserted} pour reporting.
    """
    from server.config import DATA_DIR

    sujets_path = DATA_DIR / "sujets" / "latest.json"
    if not sujets_path.exists():
        raise FileNotFoundError(
            f"{sujets_path} introuvable — lance d'abord "
            "`python -m server.cli score`"
        )

    sujets_payload = json.loads(sujets_path.read_text(encoding="utf-8"))

    return {
        "sujets_snapshots": snapshot_sujets(sujets_payload),
        "topic_pulse": snapshot_topics(sujets_payload),
        "category_pulse": snapshot_categories(),
        "source_pulse": snapshot_sources(sujets_payload.get("sources_used") or {}),
    }


# ---------------------------------------------------------------
# Stats : pour vérifier l'état de la DB
# ---------------------------------------------------------------


def stats() -> dict[str, Any]:
    """Retourne row counts + dernier snapshot par table."""
    with _connect() as conn:
        with conn.cursor() as cur:
            out: dict[str, Any] = {}
            for table in (
                "sujets_snapshots",
                "topic_pulse",
                "category_pulse",
                "source_pulse",
            ):
                cur.execute(
                    f"SELECT COUNT(*), MIN(snapshot_at), MAX(snapshot_at) "
                    f"FROM {table}"
                )
                count, first, last = cur.fetchone()
                out[table] = {
                    "rows": count,
                    "first_snapshot": first.isoformat() if first else None,
                    "last_snapshot": last.isoformat() if last else None,
                }
            return out
