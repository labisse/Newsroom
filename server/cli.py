"""CLI orchestrateur — fetch des sources + scoring.

Usage :
    python -m server.cli fetch-all                 # toutes les sources
    python -m server.cli fetch msn                 # une source
    python -m server.cli fetch msn x_trends        # plusieurs sources
    python -m server.cli score                     # agrège à partir des snapshots
    python -m server.cli all                       # fetch-all puis score

Sources : msn, wikimedia, google_trends, x_trends
Sortie  : data/{source}/{YYYY-MM-DD}.json + data/{source}/latest.json
          data/sujets/latest.json (sortie scoring)
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from typing import Any, Callable

from server.scoring import aggregator
from server.sources import (
    discoversnoop,
    google_news,
    google_trends,
    msn,
    wikimedia,
    x_trends,
)

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

    args = parser.parse_args(argv)

    if args.cmd == "fetch-all":
        return cmd_fetch_all()
    if args.cmd == "fetch":
        return cmd_fetch(args.sources)
    if args.cmd == "score":
        return cmd_score(args.top)
    if args.cmd == "all":
        return cmd_all(args.top)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
