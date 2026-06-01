"""Pipeline de labelling pour le futur modele predictif Discover (B1).

Pour chaque sujet detecte (snapshot data/sujets/{date}.json), on matche
semantiquement son titre contre le `discover_history.jsonl` de chaque
projet GSC connecte. Si on trouve un article du projet avec une
similarite > 0.78 ET dont `last_seen_at` est posterieur a la date de
detection du sujet, on label = 1 (le sujet a vraiment atterri sur
Discover du projet apres qu'on l'ait detecte). Sinon label = 0.

Output append-only : `data/training/labeled_sujets.jsonl`.
Cle d'unicite : (sujet_id, project, detected_at). On skip les
combinaisons deja labellisees au prochain run.

Usage :
  python -m server.cli predict-label              # incremental (latest)
  python -m server.cli predict-label --backfill   # tous les snapshots

L'output servira de training data pour le modele predictif Discover
quand on aura 30-60 jours d'accumulation. En attendant, il permet
deja de mesurer le taux de "hit Discover" du systeme (combien de
nos sujets atterrissent vraiment).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from server.config import DATA_DIR
from server.sources import gsc as gsc_mod
from server.sources import gsc_rag

# Seuil cosine pour considerer qu'un article GSC matche un sujet detecte.
# Aligne sur les autres pipelines semantiques (semantic_dedup, weak_signals).
MATCH_THRESHOLD = 0.78

# Tolerance temporelle : GSC Discover indexe avec un peu de latence,
# donc on accepte un match dont last_seen_at est jusqu'a TOLERANCE_HOURS
# AVANT la detection du sujet. Au-dela, c'est un match historique (l'URL
# etait deja sur Discover avant qu'on detecte le sujet) → label ambigu
# qu'on exclut du training data.
TOLERANCE_HOURS_BEFORE_DETECTION = 12

# Apres detection, on attend jusqu'a HORIZON_HOURS avant de considerer
# que le sujet n'a pas atterri. Si on labellise un sujet trop tot (moins
# de cette duree post-detection), on l'exclut (label=null) car la
# fenetre n'est pas fermee.
HORIZON_HOURS = 48

TRAINING_DIR = DATA_DIR / "training"
LABELED_PATH = TRAINING_DIR / "labeled_sujets.jsonl"


def _load_jsonl_indexed_by_url(path: Path) -> dict[str, dict[str, Any]]:
    """Charge un JSONL et retourne {url: entry}."""
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                url = entry.get("url")
                if url:
                    out[url] = entry
            except json.JSONDecodeError:
                continue
    return out


def _parse_iso(s: str | None) -> datetime | None:
    """Parse un ISO 8601 string en datetime UTC. None si invalide."""
    if not s:
        return None
    try:
        # Supporte "Z" final et offset
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _extract_features(sujet: dict[str, Any]) -> dict[str, Any]:
    """Extrait les features ML d'un sujet pour le futur modele."""
    breakdown = sujet.get("score_breakdown") or {}
    enrich = sujet.get("llm_enrich") or {}
    signals = sujet.get("signals") or []
    sources_hit = {s.get("label") or s.get("source") for s in signals}
    sources_hit.discard(None)

    return {
        "score": int(sujet.get("score") or 0),
        "tier": sujet.get("tier") or "low",
        "breakdown": {
            k: float(v) for k, v in breakdown.items()
            if k != "total" and isinstance(v, (int, float))
        },
        "n_signals": len(signals),
        "sources_hit": sorted(s for s in sources_hit if s),
        "has_discover_signal": "discover" in sources_hit,
        "has_msn_signal": "msn" in sources_hit,
        "has_gnews_signal": "gnews" in sources_hit,
        "has_trends_signal": "trends" in sources_hit,
        "has_wiki_signal": "wiki" in sources_hit,
        "has_youtube_signal": "youtube" in sources_hit,
        "has_tiktok_signal": "tiktok" in sources_hit,
        "has_x_signal": "x" in sources_hit,
        # Enrichissements
        "trend": sujet.get("trend") or "new",
        "velocity_6h": sujet.get("velocity_6h"),
        "velocity_24h": sujet.get("velocity_24h"),
        "cluster_size": int(sujet.get("cluster_size") or 1),
        "llm_main_topic": enrich.get("main_topic") or "",
        "llm_categories": enrich.get("categories") or [],
        "llm_entities": enrich.get("entities") or [],
        "llm_sentiment": enrich.get("sentiment") or "neutral",
        "llm_ton": enrich.get("ton") or "factuel",
        # Discover heuristiques deja calculees par aggregator
        "discover_category": sujet.get("discover_category") or "",
        "n_discover_entities": len(sujet.get("discover_entities") or []),
    }


def _build_label_key(sujet_id: str, project: str, detected_at: str) -> str:
    """Cle d'unicite stable pour dedup les labels."""
    raw = f"{sujet_id}|{project}|{detected_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _load_existing_keys() -> set[str]:
    """Charge les cles deja presentes dans labeled_sujets.jsonl."""
    keys: set[str] = set()
    if not LABELED_PATH.exists():
        return keys
    with LABELED_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                k = entry.get("key")
                if k:
                    keys.add(k)
            except json.JSONDecodeError:
                continue
    return keys


def _append_labels(labels: list[dict[str, Any]]) -> int:
    """Append au JSONL training. Retourne nb effectivement ecrits."""
    if not labels:
        return 0
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    with LABELED_PATH.open("a", encoding="utf-8") as f:
        for lbl in labels:
            f.write(json.dumps(lbl, ensure_ascii=False) + "\n")
    return len(labels)


def _label_one_sujet(
    sujet: dict[str, Any],
    detected_at: datetime,
    project: str,
    url_index: dict[str, dict[str, Any]],
    horizon_cutoff: datetime,
) -> dict[str, Any] | None:
    """Match semantique + label pour 1 sujet sur 1 projet.

    Retourne None si la fenetre d'observation n'est pas encore atteinte
    (sujet trop recent : detected_at + HORIZON_HOURS > now). Sinon
    retourne le dict labelise pret a append.
    """
    title = sujet.get("title") or ""
    if not title.strip():
        return None

    # Fenetre pas encore observable
    if detected_at + timedelta(hours=HORIZON_HOURS) > horizon_cutoff:
        return None

    # Recherche semantique dans l'index GSC du projet
    try:
        matches = gsc_rag.search_similar(project, title, top_k=3)
    except RuntimeError:
        # Index pas encore construit : on ne peut pas labelliser
        return None

    best = matches[0] if matches else None
    sim = float(best.get("similarity", 0)) if best else 0.0

    label = 0
    match_data: dict[str, Any] | None = None
    if best and sim >= MATCH_THRESHOLD:
        url = best.get("url", "")
        gsc_entry = url_index.get(url) or {}
        last_seen = _parse_iso(gsc_entry.get("last_seen_at"))
        threshold_dt = detected_at - timedelta(hours=TOLERANCE_HOURS_BEFORE_DETECTION)
        if last_seen and last_seen >= threshold_dt:
            label = 1
            match_data = {
                "url": url,
                "title": best.get("title", ""),
                "similarity": round(sim, 3),
                "last_seen_at": gsc_entry.get("last_seen_at"),
                "clicks_total": int(gsc_entry.get("clicks_total", 0)),
                "impressions_total": int(gsc_entry.get("impressions_total", 0)),
            }
        # Si match semantique fort MAIS last_seen anterieur a detection-12h :
        # c'etait deja sur Discover avant — label ambigu, on garde 0 mais on
        # note le match historique pour analyse.

    sujet_id = sujet.get("id") or ""
    detected_at_iso = detected_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "key": _build_label_key(sujet_id, project, detected_at_iso),
        "labeled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sujet_id": sujet_id,
        "sujet_title": title,
        "sujet_detected_at": detected_at_iso,
        "project": project,
        "label": label,
        "match": match_data,
        "best_similarity": round(sim, 3),
        "features": _extract_features(sujet),
    }


def _label_snapshot(
    snapshot_payload: dict[str, Any],
    projects: list[str],
    existing_keys: set[str],
    horizon_cutoff: datetime,
) -> list[dict[str, Any]]:
    """Labellise un snapshot pour tous les projets connectes.

    Skip les cles deja presentes dans existing_keys.
    """
    sujets = snapshot_payload.get("sujets") or []
    if not sujets:
        return []

    detected_at = _parse_iso(snapshot_payload.get("generated_at"))
    if detected_at is None:
        return []

    # Charge l'index URL par projet une seule fois
    url_indexes: dict[str, dict[str, Any]] = {}
    for project in projects:
        jsonl = DATA_DIR / "projects" / project / "discover_history.jsonl"
        url_indexes[project] = _load_jsonl_indexed_by_url(jsonl)

    out: list[dict[str, Any]] = []
    for sujet in sujets:
        for project in projects:
            sujet_id = sujet.get("id") or ""
            detected_iso = detected_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            key = _build_label_key(sujet_id, project, detected_iso)
            if key in existing_keys:
                continue
            label = _label_one_sujet(
                sujet,
                detected_at,
                project,
                url_indexes[project],
                horizon_cutoff,
            )
            if label is not None:
                out.append(label)
                existing_keys.add(key)
    return out


def _list_connected_projects() -> list[str]:
    """Liste des projets ayant un index GSC + tokens valides."""
    projects_index = DATA_DIR / "projects" / "index.json"
    if not projects_index.exists():
        return []
    try:
        payload = json.loads(projects_index.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    slugs = [
        p.get("slug", "")
        for p in payload.get("projects", [])
        if p.get("slug")
    ]
    out: list[str] = []
    for slug in slugs:
        if not gsc_mod.is_connected(slug):
            continue
        # Verifie aussi que l'index semantique existe
        idx = DATA_DIR / "projects" / slug / "embeddings.npz"
        if not idx.exists():
            continue
        out.append(slug)
    return out


def _list_snapshot_files(*, backfill: bool) -> list[Path]:
    """Retourne les snapshots a traiter.

    - backfill=False : seulement data/sujets/latest.json
    - backfill=True : tous les data/sujets/YYYY-MM-DD.json
    """
    sujets_dir = DATA_DIR / "sujets"
    if not sujets_dir.exists():
        return []
    if backfill:
        return sorted(sujets_dir.glob("[0-9][0-9][0-9][0-9]-*.json"))
    latest = sujets_dir / "latest.json"
    return [latest] if latest.exists() else []


def label(backfill: bool = False) -> dict[str, Any]:
    """Pipeline principal.

    Args:
        backfill : si True, re-traite tous les snapshots historiques
                   (skip ceux deja labellises). Sinon, traite seulement
                   le latest.json du run en cours.

    Returns:
        Stats : projects, snapshots_processed, labels_written, hit_rate
    """
    projects = _list_connected_projects()
    if not projects:
        print("[labeler] Aucun projet GSC connecte avec index. Skip.")
        return {
            "projects": [],
            "snapshots_processed": 0,
            "labels_written": 0,
            "hit_rate": None,
        }

    snapshots = _list_snapshot_files(backfill=backfill)
    if not snapshots:
        print("[labeler] Aucun snapshot a traiter.")
        return {
            "projects": projects,
            "snapshots_processed": 0,
            "labels_written": 0,
            "hit_rate": None,
        }

    existing_keys = _load_existing_keys()
    print(
        f"[labeler] {len(snapshots)} snapshots a traiter sur {len(projects)} "
        f"projets ({len(existing_keys)} labels deja en cache)"
    )

    horizon_cutoff = datetime.now(timezone.utc)
    total_written = 0
    snapshot_count = 0
    label_counts = {0: 0, 1: 0}

    for path in snapshots:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[labeler] {path.name} : erreur lecture ({exc}), skip")
            continue

        labels = _label_snapshot(
            payload, projects, existing_keys, horizon_cutoff
        )
        if not labels:
            continue
        for lbl in labels:
            label_counts[lbl["label"]] = label_counts.get(lbl["label"], 0) + 1
        n = _append_labels(labels)
        total_written += n
        snapshot_count += 1
        print(
            f"[labeler] {path.name} : +{n} labels "
            f"(label=1: {sum(1 for l in labels if l['label']==1)}, "
            f"label=0: {sum(1 for l in labels if l['label']==0)})"
        )

    hit_rate = None
    total_labels = label_counts[0] + label_counts[1]
    if total_labels > 0:
        hit_rate = round(label_counts[1] / total_labels, 3)

    return {
        "projects": projects,
        "snapshots_processed": snapshot_count,
        "labels_written": total_written,
        "label_counts": label_counts,
        "hit_rate": hit_rate,
    }
