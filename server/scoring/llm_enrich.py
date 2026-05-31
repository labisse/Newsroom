"""LLM enrichment des sujets : entites + categories + sentiment + ton.

Pour chaque sujet produit par l'aggregator, on demande a Claude Haiku
(via Messages API en direct, comme title_generator) de retourner :

  - entities      : entites mentionnees dans le titre (personnes,
                    institutions, lieux, evenements nommes)
  - categories    : 1-3 categories canoniques parmi les 10 du systeme
  - main_topic    : phrase canonique courte (3-5 mots) qui resume le sujet
  - sentiment     : positive / neutral / negative
  - ton           : factuel / polemique / people / opinion / divers

On batch tous les sujets en 1 seul call (max 30 sujets/snapshot) pour
amortir les tokens d'instruction. Cache local par hash du titre pour
ne pas refaire l'appel sur des sujets persistants.

Couts estimes (Haiku 4.5) :
  - ~500 tokens d'instruction (caches via prompt caching potentiel)
  - ~30 sujets x 80 tokens input + 50 tokens output = ~3.9k tokens/run
  - 4 runs/jour : ~16k tokens/jour
  - Tarif Haiku : $0.80 / Mtok input, $4 / Mtok output
  - Cout journalier : <$0.05

Si ANTHROPIC_API_KEY absent : skip silencieux (champs vides).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from server.config import DATA_DIR, settings

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
TIMEOUT_S = 60
MAX_TOKENS = 4000  # Pour ~30 sujets en sortie JSON


CACHE_DIR = Path(DATA_DIR) / "cache"
CACHE_PATH = CACHE_DIR / "llm_enrich.jsonl"

# 10 categories canoniques (alignees evolution.html / categories.js)
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

SENTIMENT_VALUES = {"positive", "neutral", "negative"}
TON_VALUES = {"factuel", "polemique", "people", "opinion", "divers"}


def _norm_title_for_cache(title: str) -> str:
    """Cle de cache : titre lowercased + ponctuation collapsee."""
    norm = re.sub(r"[^\w\s]", " ", (title or "").lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, dict[str, Any]]:
    """Charge le cache JSONL en memoire. Format : 1 ligne JSON par sujet."""
    if not CACHE_PATH.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    try:
        for line in CACHE_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                out[entry["key"]] = entry["data"]
            except (json.JSONDecodeError, KeyError):
                continue
    except OSError:
        pass
    return out


def _append_cache(entries: dict[str, dict[str, Any]]) -> None:
    """Append-only : on n'ecrase jamais le cache existant."""
    if not entries:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for key, data in entries.items():
        lines.append(json.dumps({"key": key, "data": data}, ensure_ascii=False))
    with CACHE_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


SYSTEM_PROMPT = """Tu es un classifieur de sujets d'actualite francaise.

Pour chaque sujet, retourne strictement un objet JSON avec ces champs :
  - main_topic : phrase canonique de 3-5 mots qui resume le sujet
                 (ex: "Finale Ligue des champions PSG", "Mort d'Edgar Morin")
  - entities   : liste de 1-5 entites nommees (personnes, equipes, marques,
                 evenements, lieux). Pas de mots generiques.
  - categories : 1-3 categories parmi : politique, international, economie,
                 tech, sport, people, science, sante, societe, lifestyle.
                 Du plus pertinent au moins. "people" = celebrites/show-biz,
                 "societe" = faits divers/justice/education, "lifestyle" =
                 cuisine/voyage/mode.
  - sentiment  : "positive" / "neutral" / "negative" — le ton emotionnel
                 du sujet (deces, drame = negative ; victoire, decouverte
                 = positive ; reunion politique = neutral).
  - ton        : "factuel" / "polemique" / "people" / "opinion" / "divers"
                 (factuel = info brute, polemique = controverse/scandale,
                 people = celebrites/vie privee, opinion = tribune/analyse,
                 divers = autre).

Retourne UNIQUEMENT un objet JSON : {"sujets": [{...}, {...}]}
Aucun texte avant ou apres. L'ordre des sujets doit etre respecte."""


def _build_user_prompt(sujets: list[dict[str, Any]]) -> str:
    lines = ["Voici les sujets a classifier (1 par ligne, format `[id] titre`) :", ""]
    for s in sujets:
        sid = s.get("id", "?")
        title = (s.get("title") or "").strip()
        lines.append(f"[{sid}] {title}")
    lines.append("")
    lines.append('Reponds avec {"sujets": [...]} dans le meme ordre, en incluant '
                 'le champ "id" en premier.')
    return "\n".join(lines)


def _call_anthropic(sujets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Appelle l'API et parse la reponse JSON. Retourne [] si erreur."""
    user_prompt = _build_user_prompt(sujets)

    response = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": settings.anthropic_model,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        },
        timeout=TIMEOUT_S,
    )

    if response.status_code >= 400:
        try:
            err = response.json().get("error", {}).get("message", response.text)
        except (json.JSONDecodeError, ValueError):
            err = response.text
        print(f"[llm_enrich] anthropic error {response.status_code}: {err}")
        return []

    data = response.json()
    blocks = data.get("content", []) or []
    text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    text = "".join(text_parts).strip()

    # On extrait le JSON meme si le LLM le wrappe dans ```json ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"[llm_enrich] JSON parse error: {exc}. Raw: {text[:200]}")
        return []

    items = parsed.get("sujets") or parsed.get("items") or []
    if not isinstance(items, list):
        return []
    return items


def _sanitize_enrich(raw: dict[str, Any]) -> dict[str, Any]:
    """Valide + normalise la reponse LLM pour un sujet."""
    entities = raw.get("entities") or []
    if not isinstance(entities, list):
        entities = []
    entities = [str(e).strip() for e in entities if str(e).strip()][:5]

    categories = raw.get("categories") or []
    if not isinstance(categories, list):
        categories = []
    categories = [
        str(c).strip().lower()
        for c in categories
        if str(c).strip().lower() in CANONICAL_CATEGORIES
    ][:3]

    main_topic = str(raw.get("main_topic") or "").strip()[:80]

    sentiment = str(raw.get("sentiment") or "neutral").strip().lower()
    if sentiment not in SENTIMENT_VALUES:
        sentiment = "neutral"

    ton = str(raw.get("ton") or "factuel").strip().lower()
    if ton not in TON_VALUES:
        ton = "factuel"

    return {
        "main_topic": main_topic,
        "entities": entities,
        "categories": categories,
        "sentiment": sentiment,
        "ton": ton,
    }


def enrich(sujets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annote chaque sujet avec llm_enrich : {main_topic, entities,
    categories, sentiment, ton}. Mute la liste in-place et la retourne.

    Si ANTHROPIC_API_KEY absent : skip silencieux (les sujets gardent
    leurs champs existants, on ajoute juste llm_enrich=None).
    """
    if not sujets:
        return sujets

    if not settings.anthropic_api_key:
        print("[llm_enrich] ANTHROPIC_API_KEY absent : skip")
        for s in sujets:
            s["llm_enrich"] = None
        return sujets

    cache = _load_cache()

    # Sujets a envoyer au LLM : ceux qui ne sont pas en cache
    to_query: list[dict[str, Any]] = []
    cached_hits: dict[str, dict[str, Any]] = {}
    for s in sujets:
        key = _norm_title_for_cache(s.get("title") or "")
        if key in cache:
            cached_hits[s["id"]] = cache[key]
        else:
            to_query.append(s)

    print(
        f"[llm_enrich] {len(cached_hits)} cache hits, "
        f"{len(to_query)} sujets a enrichir"
    )

    fresh_results: dict[str, dict[str, Any]] = {}
    if to_query:
        # Batch en chunks de 25 pour ne pas saturer max_tokens
        for i in range(0, len(to_query), 25):
            chunk = to_query[i : i + 25]
            raw_items = _call_anthropic(chunk)
            for raw in raw_items:
                sid = str(raw.get("id") or "").strip()
                if not sid:
                    continue
                fresh_results[sid] = _sanitize_enrich(raw)

    # Annote chaque sujet
    new_cache_entries: dict[str, dict[str, Any]] = {}
    for s in sujets:
        sid = s["id"]
        enriched = cached_hits.get(sid) or fresh_results.get(sid)
        if enriched is None:
            s["llm_enrich"] = None
            continue
        s["llm_enrich"] = enriched
        # Si c'est du frais, on l'ajoute au cache
        if sid in fresh_results:
            key = _norm_title_for_cache(s.get("title") or "")
            new_cache_entries[key] = enriched

    _append_cache(new_cache_entries)
    return sujets
