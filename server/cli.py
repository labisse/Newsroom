"""CLI orchestrateur des sources.

Usage :
    python -m server.cli fetch-all
    python -m server.cli fetch msn
    python -m server.cli fetch wikimedia
    python -m server.cli fetch google_trends
    python -m server.cli fetch x_trends

Sortie : data/{source}/{YYYY-MM-DD}.json + data/{source}/latest.json
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from typing import Any, Callable

from server.sources import google_trends, msn, wikimedia, x_trends

SOURCES: dict[str, Callable[[], dict[str, Any]]] = {
    "msn": msn.run,
    "wikimedia": wikimedia.run,
    "google_trends": google_trends.run,
    "x_trends": x_trends.run,
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


def cmd_fetch(name: str) -> int:
    """Lance une source unique."""
    if name not in SOURCES:
        print(
            f"source inconnue : {name}\nsources disponibles : "
            + ", ".join(SOURCES),
            file=sys.stderr,
        )
        return 2

    ok, summary = _run_one(name)
    print(summary)

    if not ok:
        # Log la stack complète quand on cible une source unique
        traceback.print_exc()
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="editorial-signal",
        description="Collecte les signaux externes (MSN, Wikimedia, Google Trends, X)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch-all", help="Lancer toutes les sources")

    p_one = sub.add_parser("fetch", help="Lancer une source unique")
    p_one.add_argument(
        "source",
        choices=sorted(SOURCES.keys()),
        help="Nom de la source",
    )

    args = parser.parse_args(argv)

    if args.cmd == "fetch-all":
        return cmd_fetch_all()
    if args.cmd == "fetch":
        return cmd_fetch(args.source)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
