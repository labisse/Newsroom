"""Génération de titres dans le style éditorial d'un média.

Pour un sujet d'actualité donné + un échantillon de titres historiques
performants d'un site, on demande à Claude de proposer UN titre qui :
  - Couvre le sujet
  - Respecte les codes stylistiques observés (longueur, ponctuation,
    accroches, citations entre guillemets, etc.)

Utilise Anthropic Messages API en direct (requests, pas de SDK)
pour éviter une dépendance supplémentaire.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from server.config import settings

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
TIMEOUT_S = 30
MAX_TOKENS = 200


def _build_prompt(
    sujet_title: str,
    sujet_rationale: str | None,
    project_name: str,
    historical_titles: list[dict[str, Any]],
) -> str:
    """Construit le prompt utilisateur pour Claude.

    historical_titles : list de {title, clicks, similarity} — sortie
    de gsc_rag.search_similar pour le sujet (filtrée pour ne garder
    que les matches avec un vrai titre, pas un slug brut).
    """
    examples_lines: list[str] = []
    for h in historical_titles:
        title = (h.get("title") or "").strip()
        if not title:
            continue
        clicks = int(h.get("clicks", 0) or 0)
        examples_lines.append(f"- « {title} » ({clicks:,} clicks Discover)".replace(",", " "))

    examples_block = (
        "\n".join(examples_lines)
        if examples_lines
        else "(aucun titre historique pertinent — utilise le style FR éditorial premium par défaut)"
    )

    rationale_line = (
        f"\nContexte signal : {sujet_rationale}" if sujet_rationale else ""
    )

    return f"""Tu es un secrétaire de rédaction expérimenté du média **{project_name}**. Tu dois proposer UN seul titre d'article qui couvre le sujet d'actualité ci-dessous, dans le style éditorial de {project_name}.

SUJET D'ACTUALITÉ :
{sujet_title}{rationale_line}

EXEMPLES DE TITRES HISTORIQUEMENT PERFORMANTS DE {project_name} :
{examples_block}

CONSIGNES :
1. Reprends scrupuleusement les codes stylistiques observés dans les exemples : structure (citation entre guillemets « », deux-points, prénom + nom, exclamation, etc.), longueur, ton (factuel/people/sensationnel selon le pattern dominant), présence de chiffres ou de citations.
2. 80–140 caractères idéalement.
3. Le titre doit être en français, prêt à publier.
4. Pas de méta-commentaire, pas de phrase d'introduction — uniquement le titre, sur une seule ligne.

TITRE PROPOSÉ :"""


def generate_title(
    sujet_title: str,
    project_name: str,
    historical_titles: list[dict[str, Any]],
    *,
    sujet_rationale: str | None = None,
) -> str | None:
    """Génère un titre dans le style du média. Retourne None si pas de clé."""
    if not settings.anthropic_api_key:
        return None
    if not sujet_title:
        return None

    prompt = _build_prompt(
        sujet_title=sujet_title,
        sujet_rationale=sujet_rationale,
        project_name=project_name,
        historical_titles=historical_titles or [],
    )

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
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=TIMEOUT_S,
    )

    if response.status_code >= 400:
        try:
            err = response.json().get("error", {}).get("message", response.text)
        except (json.JSONDecodeError, ValueError):
            err = response.text
        raise RuntimeError(f"Anthropic error ({response.status_code}): {err}")

    data = response.json()
    blocks = data.get("content", [])
    if not blocks:
        return None

    # Concatène les blocs text (en pratique il y en a 1)
    text_parts = [
        block.get("text", "")
        for block in blocks
        if block.get("type") == "text"
    ]
    text = "".join(text_parts).strip()

    # Nettoyage : Claude peut retourner avec guillemets autour ou un préfixe
    cleaned = _clean_title(text)
    return cleaned or None


def _clean_title(raw: str) -> str:
    """Retire les artefacts courants : guillemets enveloppants, préfixes."""
    if not raw:
        return ""
    text = raw.strip()

    # Retire les éventuels guillemets droits OU typographiques qui enrobent
    # TOUT le titre (mais on garde ceux internes type « citation »)
    for pair in [('"', '"'), ("«", "»"), ("'", "'"), ("“", "”")]:
        if text.startswith(pair[0]) and text.endswith(pair[1]):
            inner = text[len(pair[0]) : -len(pair[1])].strip()
            # Vérifie que l'intérieur ne contient pas le même séparateur
            if pair[0] not in inner and pair[1] not in inner:
                text = inner

    # Retire les préfixes type "Titre :" ou "Proposition :"
    lowered = text.lower()
    for prefix in ("titre :", "titre:", "proposition :", "proposition:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :].strip()
            break

    # Limite à la 1re ligne (au cas où Claude ajoute des explications)
    text = text.split("\n")[0].strip()
    return text
