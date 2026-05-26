"""Helpers partagés par les fetchers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.config import DATA_DIR


def now_iso() -> str:
    """Timestamp UTC ISO 8601 (suffix Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_str() -> str:
    """Date du jour UTC au format YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def today_hour_str() -> str:
    """Date + heure UTC au format YYYY-MM-DD-HH (pour sources horaires)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")


def yesterday_path_parts() -> tuple[str, str]:
    """(YYYYMMDD, YYYY/MM/DD) pour l'API Wikimedia pageviews."""
    from datetime import timedelta

    y = datetime.now(timezone.utc) - timedelta(days=1)
    return y.strftime("%Y%m%d"), y.strftime("%Y/%m/%d")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_snapshot(source: str, payload: dict[str, Any], filename: str) -> Path:
    """Écrit le payload dans data/{source}/{filename}.json + maj latest.json."""
    out_dir = DATA_DIR / source
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = out_dir / f"{filename}.json"
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Toujours maintenir un latest.json pour le front statique
    latest_path = out_dir / "latest.json"
    latest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return snapshot_path
