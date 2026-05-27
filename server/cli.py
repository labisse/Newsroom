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

Sources : msn, wikimedia, google_trends, x_trends, discoversnoop, google_news
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
    wikimedia,
    x_trends,
)
from server.sources import gsc as gsc_mod
from server.sources import gsc_oauth_local, gsc_storage, gsc_titles

SOURCES: dict[str, Callable[[], dict[str, Any]]] = {
    "msn": msn.run,
    "wikimedia": wikimedia.run,
    "google_trends": google_trends.run,
    "x_trends": x_trends.run,
    "discoversnoop": discoversnoop.run,
    "google_news": google_news.run,
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

    # Si pas de site fourni, tenter le premier accessible
    if not site_url:
        try:
            sites = gsc_mod.get_sites(project_slug)
        except Exception as exc:  # noqa: BLE001
            print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        if not sites:
            print("✗ Aucune propriété GSC accessible.", file=sys.stderr)
            return 1
        site_url = sites[0].get("siteUrl", "")
        print(f"  Site par défaut : {site_url}")

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


def cmd_gsc_disconnect(project_slug: str) -> int:
    """Supprime les tokens d'un projet."""
    if not gsc_mod.is_connected(project_slug):
        print(f"Projet '{project_slug}' déjà déconnecté.")
        return 0
    gsc_mod.disconnect(project_slug)
    print(f"✓ Projet '{project_slug}' déconnecté de GSC.")
    return 0


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

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
