"""CLI orchestrateur — fetch des sources + scoring + GSC par projet.

Usage :
    # Sources & scoring
    python -m server.cli fetch-all                 # toutes les sources globales
    python -m server.cli fetch msn                 # une source
    python -m server.cli fetch msn x_trends        # plusieurs sources
    python -m server.cli score                     # agrège à partir des snapshots
    python -m server.cli all                       # fetch-all puis score

    # GSC par projet
    python -m server.cli gsc-connect --project=<slug>          # OAuth flow local
    python -m server.cli gsc-status                            # liste les projets connectés
    python -m server.cli gsc-sites --project=<slug>            # sites accessibles
    python -m server.cli gsc-fetch --project=<slug> [--site=URL] [--days=365]
    python -m server.cli gsc-scrape-titles --project=<slug> [--limit=N]
    python -m server.cli gsc-disconnect --project=<slug>

    # PostgreSQL time-series (DigitalOcean Managed Postgres)
    python -m server.cli db-init        # crée les tables (1× au début)
    python -m server.cli db-snapshot    # insère un snapshot après `score`
    python -m server.cli db-stats       # rows + dates par table

Sources : msn, wikimedia, google_trends, x_trends, discoversnoop, google_news,
          reddit, youtube_trending
Sortie  : data/{source}/{YYYY-MM-DD}.json + data/{source}/latest.json
          data/sujets/latest.json (sortie scoring)
          data/projects/{slug}/gsc_tokens.json (OAuth)
          data/projects/{slug}/discover_history.jsonl (extraction GSC)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from typing import Any, Callable

from server.config import DATA_DIR
from server.scoring import aggregator
from server.sources import (
    discoversnoop,
    google_news,
    google_trends,
    msn,
    reddit,
    wikimedia,
    x_trends,
    youtube_trending,
)
from server.sources import gsc as gsc_mod
from server.sources import (
    gsc_insights,
    gsc_oauth_local,
    gsc_rag,
    gsc_storage,
    gsc_titles,
)

SOURCES: dict[str, Callable[[], dict[str, Any]]] = {
    "msn": msn.run,
    "wikimedia": wikimedia.run,
    "google_trends": google_trends.run,
    "x_trends": x_trends.run,
    "discoversnoop": discoversnoop.run,
    "google_news": google_news.run,
    "reddit": reddit.run,
    "youtube_trending": youtube_trending.run,
}


def _run_one(name: str) -> tuple[bool, str]:
    """Lance une source. Retourne (ok, summary)."""
    if name not in SOURCES:
        return False, f"source inconnue : {name}"

    started = time.perf_counter()
    try:
        payload = SOURCES[name]()
    except Exception as exc:  # noqa: BLE001 — résumé d'erreur lisible
        elapsed = time.perf_counter() - started
        return False, f"{name:14s}  ✗  {type(exc).__name__}: {exc}  ({elapsed:.2f}s)"

    elapsed = time.perf_counter() - started

    # Compteur lisible selon le format de chaque source
    if "count" in payload:
        details = f"{payload['count']} items"
    elif "windows" in payload:
        details = ", ".join(
            f"{w}={data['count']}" for w, data in payload["windows"].items()
        )
    else:
        details = "ok"

    return True, f"{name:14s}  ✓  {details}  ({elapsed:.2f}s)"


def cmd_fetch_all() -> int:
    """Lance tous les fetchers en séquence."""
    print("Editorial Signal — fetch-all\n")
    print("-" * 60)

    failures = 0
    for name in SOURCES:
        ok, summary = _run_one(name)
        print(summary)
        if not ok:
            failures += 1

    print("-" * 60)
    total = len(SOURCES)
    ok_count = total - failures
    print(f"Terminé : {ok_count}/{total} sources OK")
    return 0 if failures == 0 else 1


def cmd_fetch(names: list[str]) -> int:
    """Lance une ou plusieurs sources nommées.

    Échoue à 1 dès qu'une source échoue, mais continue les suivantes
    pour donner un tableau de bord complet.
    """
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        print(
            f"source(s) inconnue(s) : {', '.join(unknown)}\n"
            f"sources disponibles : {', '.join(SOURCES)}",
            file=sys.stderr,
        )
        return 2

    print(f"Editorial Signal — fetch {' '.join(names)}\n")
    print("-" * 60)

    failures = 0
    for name in names:
        ok, summary = _run_one(name)
        print(summary)
        if not ok:
            failures += 1

    print("-" * 60)
    total = len(names)
    print(f"Terminé : {total - failures}/{total} sources OK")
    return 0 if failures == 0 else 1


def cmd_score(top_n: int) -> int:
    """Lance l'agrégation + scoring à partir des snapshots."""
    print("Editorial Signal — scoring\n")
    started = time.perf_counter()
    try:
        payload = aggregator.run(top_n=top_n)
    except FileNotFoundError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    elapsed = time.perf_counter() - started
    totals = payload["totals"]
    print("-" * 60)
    print(f"Sujets retenus : {totals['kept']} / {totals['candidates_scored']} candidats")
    print(
        "Par tier       : "
        f"high={totals['by_tier']['high']}  "
        f"medium={totals['by_tier']['medium']}  "
        f"low={totals['by_tier']['low']}"
    )
    print(f"Temps          : {elapsed:.2f}s")
    print("-" * 60)

    print("\nTop 5 :")
    for sujet in payload["sujets"][:5]:
        title = sujet["title"][:78] + ("…" if len(sujet["title"]) > 78 else "")
        print(f"  [{sujet['score']:>3}] {title}")

    return 0


def cmd_all(top_n: int) -> int:
    """Fetch toutes les sources puis lance le scoring."""
    code = cmd_fetch_all()
    if code != 0:
        return code
    print()
    return cmd_score(top_n=top_n)


# ============================================================
# COMMANDES GSC (par projet)
# ============================================================


def cmd_gsc_connect(project_slug: str) -> int:
    """Lance le flow OAuth Google + persiste les tokens du projet."""
    print(f"Editorial Signal — GSC connect [{project_slug}]\n")
    try:
        tokens = gsc_oauth_local.run_oauth_flow(project_slug)
    except Exception as exc:  # noqa: BLE001
        print(f"\n✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("\n✓ Connexion réussie.")
    print(f"  Tokens : data/projects/{project_slug}/gsc_tokens.json")
    print(f"  Connecté le : {tokens.get('connected_at')}")
    print()
    print(
        f"  Prochaine étape : python -m server.cli gsc-sites --project={project_slug}"
    )
    return 0


def cmd_gsc_status() -> int:
    """Liste les projets ayant des tokens GSC."""
    projects_dir = DATA_DIR / "projects"
    if not projects_dir.exists():
        print("Aucun projet configuré.")
        return 0

    print("Editorial Signal — projets GSC\n")
    print(f"{'Projet':<24} {'Connecté':<10} {'URLs en base':<15} {'Top URL':<60}")
    print("-" * 110)

    any_found = False
    for project_path in sorted(projects_dir.iterdir()):
        if not project_path.is_dir():
            continue
        slug = project_path.name
        connected = gsc_mod.is_connected(slug)
        st = gsc_storage.stats(slug)
        top = st["top_url"]
        top_line = (
            f"{top['clicks']:>8} clicks · {top['url'][:48]}"
            if top
            else "—"
        )
        print(
            f"{slug:<24} {'oui' if connected else 'non':<10} "
            f"{st['total_urls']:<15} {top_line:<60}"
        )
        any_found = True

    if not any_found:
        print("(aucun)")
    return 0


def cmd_gsc_sites(project_slug: str) -> int:
    """Liste les propriétés GSC accessibles par ce projet."""
    print(f"Editorial Signal — GSC sites [{project_slug}]\n")
    try:
        sites = gsc_mod.get_sites(project_slug)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if not sites:
        print("(aucune propriété — vérifie que ton compte Google a accès "
              "à au moins une propriété Search Console)")
        return 0

    print(f"{'Site URL':<60} {'Permission':<20}")
    print("-" * 80)
    for s in sites:
        print(
            f"{s.get('siteUrl', ''):<60} "
            f"{s.get('permissionLevel', ''):<20}"
        )
    return 0


def _resolve_project_site(project_slug: str) -> str | None:
    """Retourne le site_url GSC qui correspond au `domain` déclaré dans
    data/projects/index.json. None si pas de domain configuré."""
    projects_index = DATA_DIR / "projects" / "index.json"
    if not projects_index.exists():
        return None
    try:
        payload = json.loads(projects_index.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    for p in payload.get("projects", []):
        if p.get("slug") == project_slug:
            domain = (p.get("domain") or "").strip()
            if not domain:
                return None
            # On tente d'abord la forme sc-domain (couvre tous sous-domaines)
            # puis https://www. en fallback — resolve_site_url côté API GSC
            # fera le match exact.
            return f"sc-domain:{domain}"
    return None


def cmd_gsc_fetch(project_slug: str, site_url: str | None, days: int) -> int:
    """Extrait les URLs Discover sur N jours et upsert dans le JSONL projet."""
    print(f"Editorial Signal — GSC fetch [{project_slug}] (Discover, {days}j)\n")

    if not gsc_mod.is_connected(project_slug):
        print(
            f"✗ Projet '{project_slug}' non connecté. Lance d'abord :",
            file=sys.stderr,
        )
        print(
            f"  python -m server.cli gsc-connect --project={project_slug}",
            file=sys.stderr,
        )
        return 2

    # Stratégie de résolution du site_url :
    #   1. CLI explicite (--site=URL) prend toujours la priorité
    #   2. Sinon, on tente le domain déclaré dans data/projects/index.json
    #   3. En dernier recours seulement, on prend la 1re propriété accessible
    if not site_url:
        from_config = _resolve_project_site(project_slug)
        if from_config:
            site_url = from_config
            print(f"  Site (depuis config projet) : {site_url}")
        else:
            try:
                sites = gsc_mod.get_sites(project_slug)
            except Exception as exc:  # noqa: BLE001
                print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
                return 1
            if not sites:
                print("✗ Aucune propriété GSC accessible.", file=sys.stderr)
                return 1
            site_url = sites[0].get("siteUrl", "")
            print(f"  ⚠ Aucun domain dans index.json pour ce projet —")
            print(f"    fallback sur la 1re propriété : {site_url}")

    started = time.perf_counter()
    try:
        payload = gsc_mod.fetch_discover_12m(project_slug, site_url, days=days)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    rows = payload["rows"]
    elapsed = time.perf_counter() - started
    print(f"  {len(rows)} URLs récupérées en {elapsed:.1f}s")
    print(f"  Période : {payload['start_date']} → {payload['end_date']}")

    upsert = gsc_storage.upsert_discover_rows(project_slug, rows)
    print(
        f"  Upsert : +{upsert['inserted']} nouvelles · "
        f"~{upsert['updated']} mises à jour · {upsert['total']} total"
    )
    print(
        f"  Fichier : data/projects/{project_slug}/discover_history.jsonl"
    )
    return 0


def cmd_gsc_scrape_titles(project_slug: str, limit: int | None) -> int:
    """Scrape les titres des URLs sans titre encore récupéré."""
    print(f"Editorial Signal — GSC scrape titres [{project_slug}]\n")
    pending = gsc_storage.items_missing_title(project_slug, limit=limit)
    if not pending:
        print("Aucun titre à scraper (tous récupérés ou base vide).")
        return 0

    print(f"  À scraper : {len(pending)} URLs (politesse ~0.5s/req)")

    def on_progress(done: int, total: int, url: str) -> None:
        if done % 10 == 0 or done == total:
            print(f"  [{done:>4}/{total}] {url[:80]}")

    started = time.perf_counter()
    result = gsc_titles.scrape_missing_titles(
        project_slug, limit=limit, on_progress=on_progress
    )
    elapsed = time.perf_counter() - started

    print(
        f"\n  ✓ Scrapé : {result['scraped']} · "
        f"Échec : {result['failed']} · "
        f"Restant : {result['remaining']} · "
        f"({elapsed:.0f}s)"
    )
    return 0


def cmd_db_init() -> int:
    """Crée les 4 tables time-series + index (idempotent)."""
    from server.storage import timeseries

    print("Editorial Signal — DB init (PostgreSQL)\n")
    if not timeseries.is_enabled():
        print("✗ DATABASE_URL non définie ou psycopg non installé.")
        print("  → Configure DATABASE_URL dans .env")
        print("  → pip install -r requirements.txt")
        return 1

    started = time.perf_counter()
    try:
        timeseries.init_schema()
    except Exception as exc:  # noqa: BLE001
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    print(f"  ✓ Schéma créé/vérifié ({elapsed:.2f}s)")
    print("    Tables : sujets_snapshots, topic_pulse, category_pulse, source_pulse")
    return 0


def cmd_db_snapshot() -> int:
    """Insère un snapshot complet dans les 4 tables time-series.

    Lit data/sujets/latest.json (déjà généré par `score`) et les snapshots
    sources brutes pour calculer le snapshot par catégorie canonique.
    """
    from server.storage import timeseries

    print("Editorial Signal — DB snapshot (PostgreSQL)\n")
    if not timeseries.is_enabled():
        print("✗ DATABASE_URL non définie ou psycopg non installé.")
        return 1

    started = time.perf_counter()
    try:
        result = timeseries.snapshot_all()
    except FileNotFoundError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1
    elapsed = time.perf_counter() - started

    print(f"  ✓ Snapshot inséré ({elapsed:.2f}s)")
    for table, rows in result.items():
        print(f"    {table:22s} +{rows:>5} lignes")
    return 0


def cmd_db_stats() -> int:
    """Affiche les stats par table : nb de lignes + premier/dernier snapshot."""
    from server.storage import timeseries

    print("Editorial Signal — DB stats (PostgreSQL)\n")
    if not timeseries.is_enabled():
        print("✗ DATABASE_URL non définie ou psycopg non installé.")
        return 1

    try:
        s = timeseries.stats()
    except Exception as exc:  # noqa: BLE001
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    for table, info in s.items():
        print(f"  {table}")
        print(f"    Lignes        : {info['rows']:>8}")
        print(f"    1er snapshot  : {info['first_snapshot'] or '—'}")
        print(f"    Dernier       : {info['last_snapshot'] or '—'}")
        print()
    return 0


def cmd_secrets_export() -> int:
    """Affiche tous les secrets GitHub à configurer (workflows CI).

    Lit les valeurs depuis le .env local et imprime ce qu'il faut
    copier dans Settings → Secrets and variables → Actions.
    Ne stocke rien, n'envoie rien — juste un dump local.
    """
    from server.config import settings as _s

    print("Editorial Signal — Secrets GitHub à configurer\n")
    print("→ https://github.com/labisse/Newsroom/settings/secrets/actions\n")

    blocks = [
        (
            "fetch-and-score.yml (light + full)",
            [
                ("MSN_API_KEY", _s.msn_api_key),
                ("SERPAPI_KEY", _s.serpapi_key),
                ("WIKIMEDIA_USER_AGENT", _s.wikimedia_user_agent),
                ("DISCOVERSNOOP_EMAIL", _s.discoversnoop_email),
                ("DISCOVERSNOOP_PASSWORD", _s.discoversnoop_password),
            ],
        ),
        (
            "gsc-daily.yml (OAuth + RAG)",
            [
                ("GSC_CLIENT_ID", _s.gsc_client_id),
                ("GSC_CLIENT_SECRET", _s.gsc_client_secret),
                # Note : le refresh token par projet est récupérable
                # individuellement via `gsc-export-secret --project=<slug>`
                ("VOYAGE_API_KEY", _s.voyage_api_key),
            ],
        ),
    ]

    for title, items in blocks:
        print(f"━━━ {title} ━━━")
        for name, value in items:
            status = "✓ présent" if value else "✗ MANQUANT dans .env"
            value_display = value if value else "(vide — édite ton .env)"
            print(f"  Name  : {name}")
            print(f"  Value : {value_display}")
            print(f"  État  : {status}")
            print()

    print("━━━ Refresh tokens GSC par projet ━━━")
    print("  python -m server.cli gsc-export-secret --project=<slug>")
    print()
    print("⚠️ Ne partage JAMAIS ces valeurs publiquement.")
    return 0


def cmd_gsc_disconnect(project_slug: str) -> int:
    """Supprime les tokens d'un projet."""
    if not gsc_mod.is_connected(project_slug):
        print(f"Projet '{project_slug}' déjà déconnecté.")
        return 0
    gsc_mod.disconnect(project_slug)
    print(f"✓ Projet '{project_slug}' déconnecté de GSC.")
    return 0


def cmd_gsc_embed(
    project_slug: str,
    limit: int | None,
    backend: str | None,
) -> int:
    """Génère ou régénère l'index sémantique d'un projet."""
    print(f"Editorial Signal — GSC embed [{project_slug}]\n")

    def on_progress(stage: str, current: int, total: int) -> None:
        label = {
            "prepare": "Préparation des textes",
            "fit_tfidf": "Fit TF-IDF (vocab)",
            "embed": "Embedding",
            "save": "Sauvegarde",
        }.get(stage, stage)
        print(f"  → {label} ({total} items)")

    started = time.perf_counter()
    try:
        meta = gsc_rag.build_index(
            project_slug,
            limit=limit,
            backend=backend,
            on_progress=on_progress,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1
    elapsed = time.perf_counter() - started

    print(f"\n  ✓ Index sémantique généré ({elapsed:.1f}s)")
    print(f"    Backend  : {meta['backend']}")
    print(f"    Dimension: {meta['dim']}")
    print(f"    Vecteurs : {meta['count']}")
    print(
        f"    Sources  : {meta['used_titles']} titres scrapés, "
        f"{meta['used_slugs']} via slug nettoyé"
    )
    print(f"    Fichier  : data/projects/{project_slug}/embeddings.npz")
    return 0


def cmd_gsc_search(
    project_slug: str,
    query: str,
    top_k: int,
    rerank_by_clicks: bool,
) -> int:
    """Recherche sémantique top-K dans l'historique d'un projet."""
    print(f"Editorial Signal — GSC search [{project_slug}]\n")
    print(f'  Query : "{query}"')
    if rerank_by_clicks:
        print("  Re-ranking par clicks Discover activé")
    print()

    try:
        results = gsc_rag.search_similar(
            project_slug,
            query,
            top_k=top_k,
            rerank_by_clicks=rerank_by_clicks,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if not results:
        print("(aucun résultat)")
        return 0

    for i, r in enumerate(results, 1):
        title = r["title"] or "(slug)"
        print(
            f"  #{i:>2} sim={r['similarity']:.3f}"
            f" · {r['clicks']:>7,} clicks".replace(",", " ")
        )
        print(f"      {title[:100]}")
        print(f"      {r['url'][:100]}")
        print()
    return 0


def cmd_gsc_insights(project_slug: str) -> int:
    """Génère le JSON d'insights pré-calculé pour le front statique."""
    print(f"Editorial Signal — GSC insights [{project_slug}]\n")

    started = time.perf_counter()
    try:
        payload = gsc_insights.run(project_slug)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1
    elapsed = time.perf_counter() - started

    s = payload["stats"]
    src = payload["sujets_source"]
    ins = payload["insights"]
    print(f"  ✓ Insights générés ({elapsed:.1f}s)")
    print(
        f"    Stats   : {s['total_urls']:,} URLs · "
        f"{s['total_clicks']:,} clicks · "
        f"{s['with_title']} titres scrapés".replace(",", " ")
    )
    print(
        f"    RAG     : {len(ins['by_category'])} catégories · "
        f"{len(ins['by_entity_cluster'])} clusters · "
        f"{len(ins['by_entity'])} entités"
    )
    if not src["available"]:
        print(
            "    ⚠ data/sujets/latest.json absent — sections RAG vides. "
            "Lance `python -m server.cli score` d'abord."
        )
    print(f"    Fichier : data/projects/{project_slug}/insights.json")
    return 0


def cmd_gsc_export_secret(project_slug: str) -> int:
    """Affiche le refresh token + nom du secret GitHub à créer."""
    try:
        refresh_token = gsc_mod.get_refresh_token(project_slug)
    except RuntimeError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    env_name = gsc_mod.env_var_name_for(project_slug)
    print(f"Editorial Signal — Export secret GSC [{project_slug}]\n")
    print("→ Va sur https://github.com/labisse/Newsroom/settings/secrets/actions")
    print("→ Clique 'New repository secret' et ajoute :\n")
    print(f"  Name  : {env_name}")
    print(f"  Value : {refresh_token}")
    print()
    print("⚠️ Ne partage JAMAIS ce token. Il permet l'accès en lecture")
    print("   aux données Search Console du site connecté.")
    print()
    print("Secrets requis pour le workflow gsc-daily.yml :")
    print("  - GSC_CLIENT_ID")
    print("  - GSC_CLIENT_SECRET")
    print(f"  - {env_name}")
    return 0


def _discover_connected_projects() -> list[str]:
    """Liste les projets ayant un token GSC (fichier local ou env var).

    Lit data/projects/index.json (config officielle) et garde ceux
    pour lesquels gsc.is_connected() retourne True.
    """
    projects_index = DATA_DIR / "projects" / "index.json"
    if not projects_index.exists():
        return []
    try:
        payload = json.loads(projects_index.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    slugs = [p.get("slug", "") for p in payload.get("projects", []) if p.get("slug")]
    return [s for s in slugs if gsc_mod.is_connected(s)]


def cmd_gsc_sync_all(
    days: int,
    scrape_titles: bool,
    scrape_limit: int,
) -> int:
    """Synchronise tous les projets connectés (fetch + optionnellement scrape).

    Conçu pour être appelé par le workflow GitHub Action gsc-daily.yml.
    """
    print(f"Editorial Signal — GSC sync-all (Discover {days}j)\n")

    slugs = _discover_connected_projects()
    if not slugs:
        print("Aucun projet GSC connecté. Vérifie :")
        print("  - data/projects/index.json existe et liste les projets")
        print("  - chaque projet a soit un fichier gsc_tokens.json local,")
        print(f"    soit une env var {gsc_mod.env_var_name_for('<SLUG>')}")
        return 0

    print(f"Projets à synchroniser : {', '.join(slugs)}\n")

    overall_failures = 0
    for slug in slugs:
        print(f"━━━ {slug} ━━━")
        try:
            # Fetch Discover URLs
            # Priorité au domain déclaré dans index.json (cf gsc-fetch)
            site_url = _resolve_project_site(slug)
            if not site_url:
                sites = gsc_mod.get_sites(slug)
                if not sites:
                    print(f"  ⚠ aucun site accessible pour {slug}, skip")
                    continue
                site_url = sites[0].get("siteUrl", "")
                print(f"  Site (fallback 1re propriété) : {site_url}")
            else:
                print(f"  Site (depuis config projet) : {site_url}")

            started = time.perf_counter()
            payload = gsc_mod.fetch_discover_12m(slug, site_url, days=days)
            elapsed = time.perf_counter() - started
            print(
                f"  Fetch : {len(payload['rows'])} URLs en {elapsed:.1f}s"
            )

            up = gsc_storage.upsert_discover_rows(slug, payload["rows"])
            print(
                f"  Upsert : +{up['inserted']} · ~{up['updated']} · "
                f"{up['total']} total"
            )

            # Scrape titres (optionnel)
            if scrape_titles:
                pending = gsc_storage.items_missing_title(slug, limit=scrape_limit)
                if pending:
                    print(
                        f"  Scrape : {len(pending)} titres "
                        f"(politesse {len(pending) * 0.5:.0f}s estimé)"
                    )
                    started = time.perf_counter()
                    result = gsc_titles.scrape_missing_titles(
                        slug, limit=scrape_limit
                    )
                    elapsed = time.perf_counter() - started
                    print(
                        f"  Titres : +{result['scraped']} OK · "
                        f"{result['failed']} échec · "
                        f"{result['remaining']} restants ({elapsed:.0f}s)"
                    )
                else:
                    print("  Scrape : aucun titre manquant.")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {type(exc).__name__}: {exc}", file=sys.stderr)
            overall_failures += 1

        print()

    print("━" * 60)
    print(
        f"Terminé : {len(slugs) - overall_failures}/{len(slugs)} projets OK"
    )
    return 0 if overall_failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="editorial-signal",
        description="Collecte les signaux externes + scoring composite",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch-all", help="Lancer toutes les sources")

    p_one = sub.add_parser("fetch", help="Lancer une ou plusieurs sources nommées")
    p_one.add_argument(
        "sources",
        nargs="+",
        choices=sorted(SOURCES.keys()),
        metavar="source",
        help="Nom(s) de source(s) (ex: msn x_trends)",
    )

    p_score = sub.add_parser("score", help="Agrège + score à partir des snapshots")
    p_score.add_argument(
        "--top",
        type=int,
        default=aggregator.TOP_N,
        help=f"Nombre de sujets à garder (défaut {aggregator.TOP_N})",
    )

    p_all = sub.add_parser("all", help="fetch-all puis score")
    p_all.add_argument("--top", type=int, default=aggregator.TOP_N)

    # ── Commandes GSC ──
    p_gsc_conn = sub.add_parser(
        "gsc-connect", help="OAuth Google + persiste les tokens pour un projet"
    )
    p_gsc_conn.add_argument("--project", required=True, help="Slug du projet")

    sub.add_parser("gsc-status", help="Liste les projets connectés à GSC")

    p_gsc_sites = sub.add_parser(
        "gsc-sites", help="Liste les propriétés GSC accessibles d'un projet"
    )
    p_gsc_sites.add_argument("--project", required=True)

    p_gsc_fetch = sub.add_parser(
        "gsc-fetch", help="Extrait les URLs Discover 12 mois pour un projet"
    )
    p_gsc_fetch.add_argument("--project", required=True)
    p_gsc_fetch.add_argument(
        "--site", default=None, help="URL de la propriété (par défaut : la 1re)"
    )
    p_gsc_fetch.add_argument(
        "--days", type=int, default=365, help="Fenêtre de jours (défaut 365)"
    )

    p_gsc_scrape = sub.add_parser(
        "gsc-scrape-titles", help="Scrape les <title> des URLs sans titre"
    )
    p_gsc_scrape.add_argument("--project", required=True)
    p_gsc_scrape.add_argument(
        "--limit", type=int, default=None, help="Nb max d'URLs à scraper"
    )

    p_gsc_disc = sub.add_parser(
        "gsc-disconnect", help="Supprime les tokens GSC d'un projet"
    )
    p_gsc_disc.add_argument("--project", required=True)

    sub.add_parser(
        "secrets-export",
        help="Affiche tous les secrets GitHub à configurer (depuis .env local)",
    )

    p_gsc_export = sub.add_parser(
        "gsc-export-secret",
        help="Affiche le refresh token à ajouter en GitHub Secret (pour CI)",
    )
    p_gsc_export.add_argument("--project", required=True)

    p_gsc_sync = sub.add_parser(
        "gsc-sync-all",
        help="Sync tous les projets connectés (fetch + scrape) — pour CI",
    )
    p_gsc_sync.add_argument(
        "--days", type=int, default=365, help="Fenêtre de jours (défaut 365)"
    )
    p_gsc_sync.add_argument(
        "--scrape-titles",
        action="store_true",
        help="Scraper aussi les titres manquants",
    )
    p_gsc_sync.add_argument(
        "--scrape-limit",
        type=int,
        default=500,
        help="Nb max d'URLs à scraper par projet (défaut 500)",
    )

    p_gsc_embed = sub.add_parser(
        "gsc-embed",
        help="Génère l'index sémantique d'un projet (embeddings)",
    )
    p_gsc_embed.add_argument("--project", required=True)
    p_gsc_embed.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Nb max d'URLs à embedder (par clicks décroissants)",
    )
    p_gsc_embed.add_argument(
        "--backend",
        choices=["voyage", "tfidf"],
        default=None,
        help="Force le backend (par défaut auto-détection via .env)",
    )

    p_gsc_insights = sub.add_parser(
        "gsc-insights",
        help="Pré-calcule insights.json (stats + RAG croisés) pour le front",
    )
    p_gsc_insights.add_argument("--project", required=True)

    p_gsc_search = sub.add_parser(
        "gsc-search",
        help="Recherche sémantique top-K dans l'historique d'un projet",
    )
    p_gsc_search.add_argument("--project", required=True)
    p_gsc_search.add_argument(
        "--query", required=True, help="Texte de recherche"
    )
    p_gsc_search.add_argument(
        "--top", type=int, default=10, help="Nb de résultats (défaut 10)"
    )
    p_gsc_search.add_argument(
        "--rerank-by-clicks",
        action="store_true",
        help="Boost les contenus déjà performants par clicks historiques",
    )

    # --- PostgreSQL time-series ---
    sub.add_parser(
        "db-init",
        help="Crée les tables time-series PostgreSQL (idempotent)",
    )
    sub.add_parser(
        "db-snapshot",
        help="Insère un snapshot dans les 4 tables (après `score`)",
    )
    sub.add_parser(
        "db-stats",
        help="Affiche les stats par table (rows + dates)",
    )

    args = parser.parse_args(argv)

    if args.cmd == "fetch-all":
        return cmd_fetch_all()
    if args.cmd == "fetch":
        return cmd_fetch(args.sources)
    if args.cmd == "score":
        return cmd_score(args.top)
    if args.cmd == "all":
        return cmd_all(args.top)
    if args.cmd == "gsc-connect":
        return cmd_gsc_connect(args.project)
    if args.cmd == "gsc-status":
        return cmd_gsc_status()
    if args.cmd == "gsc-sites":
        return cmd_gsc_sites(args.project)
    if args.cmd == "gsc-fetch":
        return cmd_gsc_fetch(args.project, args.site, args.days)
    if args.cmd == "gsc-scrape-titles":
        return cmd_gsc_scrape_titles(args.project, args.limit)
    if args.cmd == "gsc-disconnect":
        return cmd_gsc_disconnect(args.project)
    if args.cmd == "gsc-export-secret":
        return cmd_gsc_export_secret(args.project)
    if args.cmd == "gsc-sync-all":
        return cmd_gsc_sync_all(
            days=args.days,
            scrape_titles=args.scrape_titles,
            scrape_limit=args.scrape_limit,
        )
    if args.cmd == "gsc-embed":
        return cmd_gsc_embed(args.project, args.limit, args.backend)
    if args.cmd == "gsc-search":
        return cmd_gsc_search(
            args.project, args.query, args.top, args.rerank_by_clicks
        )
    if args.cmd == "gsc-insights":
        return cmd_gsc_insights(args.project)
    if args.cmd == "secrets-export":
        return cmd_secrets_export()
    if args.cmd == "db-init":
        return cmd_db_init()
    if args.cmd == "db-snapshot":
        return cmd_db_snapshot()
    if args.cmd == "db-stats":
        return cmd_db_stats()

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
