"""Google Search Console — OAuth2 + extraction Discover par projet.

Port adapté de Audit Discover (services/gsc_api.py), avec :
  - Tokens stockés PAR PROJET dans data/projects/{slug}/gsc_tokens.json
    (au lieu d'un fichier unique global)
  - Pas de dépendance Flask : le mini-serveur de callback OAuth
    utilise http.server stdlib (cf server/sources/gsc_oauth_local.py)

Scopes : webmasters.readonly — strictement lecture seule.

Données extraites pour Editorial Signal :
  - URLs ayant généré du trafic Discover sur la période (jusqu'à 16 mois,
    selon ce que GSC retient ; nous demandons par défaut 365 jours)
  - Pour chaque URL : clicks Discover, impressions, CTR
  - Le titre éditorial est récupéré ensuite via scrape_titles()
    (séparé pour pouvoir incrémenter sans re-scraper systématiquement)
"""

from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

import requests

from server.config import DATA_DIR, settings

# ── Constantes API ──
GSC_API_BASE = "https://www.googleapis.com/webmasters/v3"
OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "https://www.googleapis.com/auth/webmasters.readonly"

# Limites GSC pour la pagination
GSC_MAX_ROWS_PER_CALL = 25_000
GSC_MAX_TOTAL_ROWS = 100_000  # plafond de sécurité

TIMEOUT_S = 90


# ============================================================
# CHEMINS PAR PROJET
# ============================================================


def _project_dir(project_slug: str) -> Path:
    """Dossier de stockage des données d'un projet."""
    path = DATA_DIR / "projects" / project_slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tokens_file(project_slug: str) -> Path:
    return _project_dir(project_slug) / "gsc_tokens.json"


# ============================================================
# TOKEN STORAGE (fichier JSON par projet)
# ============================================================


def _load_tokens(project_slug: str) -> dict[str, Any]:
    path = _tokens_file(project_slug)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_tokens(project_slug: str, data: dict[str, Any]) -> None:
    path = _tokens_file(project_slug)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_connected(project_slug: str) -> bool:
    """True si on a un refresh_token valide pour ce projet."""
    return bool(_load_tokens(project_slug).get("refresh_token"))


def disconnect(project_slug: str) -> None:
    """Supprime les tokens d'un projet."""
    path = _tokens_file(project_slug)
    if path.exists():
        path.unlink()


# ============================================================
# OAUTH2 FLOW
# ============================================================


def _require_oauth_config() -> None:
    if not settings.gsc_client_id or not settings.gsc_client_secret:
        raise RuntimeError(
            "GSC_CLIENT_ID ou GSC_CLIENT_SECRET manquant dans .env. "
            "Cf .env.example pour le setup côté Google Cloud Console."
        )


def get_authorization_url(project_slug: str) -> tuple[str, str]:
    """Génère l'URL d'autorisation Google OAuth2.

    Returns:
        (url, state) — state est un token CSRF à vérifier au callback.
    """
    _require_oauth_config()
    state = secrets.token_hex(16)

    # On encode le slug dans le state pour retrouver le projet au callback
    # sans avoir besoin d'un stockage serveur.
    state_with_slug = f"{state}:{project_slug}"

    params = {
        "client_id": settings.gsc_client_id,
        "redirect_uri": settings.gsc_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        # consent : force le refresh_token même si déjà accordé
        # select_account : permet de choisir le compte Google
        "prompt": "consent select_account",
        "state": state_with_slug,
    }
    url = f"{OAUTH_AUTH_URL}?{urlencode(params)}"
    return url, state_with_slug


def parse_state(state: str) -> tuple[str, str]:
    """Décode le state CSRF en (token, project_slug)."""
    if ":" not in state:
        return state, ""
    token, slug = state.split(":", 1)
    return token, slug


def exchange_code(project_slug: str, code: str) -> dict[str, Any]:
    """Échange le code d'autorisation contre access + refresh tokens.

    Sauvegarde dans data/projects/{slug}/gsc_tokens.json.
    """
    _require_oauth_config()

    response = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.gsc_client_id,
            "client_secret": settings.gsc_client_secret,
            "redirect_uri": settings.gsc_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )

    if response.status_code >= 400:
        try:
            err = response.json().get("error_description", response.text)
        except (json.JSONDecodeError, ValueError):
            err = response.text
        raise RuntimeError(f"Erreur OAuth ({response.status_code}): {err}")

    tokens = response.json()
    payload = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": time.time() + tokens.get("expires_in", 3600),
        "connected_at": datetime.now().isoformat(),
        "scopes": tokens.get("scope", SCOPES),
    }
    _save_tokens(project_slug, payload)
    return payload


def get_valid_access_token(project_slug: str) -> str:
    """Retourne un access_token valide pour le projet (refresh si expiré)."""
    tokens = _load_tokens(project_slug)
    if not tokens.get("refresh_token"):
        raise RuntimeError(
            f"Projet '{project_slug}' non connecté à GSC. "
            f"Lance : python -m server.cli gsc-connect --project={project_slug}"
        )

    expires_at = tokens.get("expires_at", 0)
    # Marge de 5 min pour anticiper l'expiration
    if time.time() + 300 >= expires_at:
        _require_oauth_config()
        response = requests.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": settings.gsc_client_id,
                "client_secret": settings.gsc_client_secret,
                "refresh_token": tokens["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        if response.status_code >= 400:
            try:
                err = response.json().get("error_description", response.text)
            except (json.JSONDecodeError, ValueError):
                err = response.text
            raise RuntimeError(
                f"Erreur refresh token ({response.status_code}): {err}"
            )

        new_tokens = response.json()
        tokens["access_token"] = new_tokens["access_token"]
        tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 3600)
        # Le refresh peut renouveler le refresh_token (rare)
        if new_tokens.get("refresh_token"):
            tokens["refresh_token"] = new_tokens["refresh_token"]
        _save_tokens(project_slug, tokens)

    return tokens["access_token"]


# ============================================================
# API CALLS
# ============================================================


def get_sites(project_slug: str) -> list[dict[str, Any]]:
    """Retourne la liste des propriétés GSC accessibles avec ces tokens."""
    access_token = get_valid_access_token(project_slug)
    response = requests.get(
        f"{GSC_API_BASE}/sites",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=30,
    )
    if response.status_code >= 400:
        try:
            err = response.json().get("error", {}).get("message", response.text)
        except (json.JSONDecodeError, ValueError):
            err = response.text
        raise RuntimeError(f"Erreur API GSC ({response.status_code}): {err}")
    return response.json().get("siteEntry", [])


def resolve_site_url(project_slug: str, site_url: str) -> str:
    """Résout le site_url vers la propriété GSC réelle.

    Teste l'URL telle quelle, puis cherche par hôte (sc-domain, www,
    http/https). Retourne l'URL fournie si aucun match — l'appelant
    recevra une erreur 403 explicite.
    """
    try:
        sites = get_sites(project_slug)
    except Exception:
        return site_url

    entries = [s.get("siteUrl", "") for s in sites if s.get("siteUrl")]
    if site_url in entries:
        return site_url

    if site_url.startswith("sc-domain:"):
        host = site_url.split(":", 1)[1].lstrip(".").lower()
    else:
        parsed = urlparse(site_url)
        host = (parsed.netloc or parsed.path).lower()
    host_bare = host.removeprefix("www.")

    # 1) Priorité sc-domain (couvre tous les sous-domaines)
    for entry in entries:
        if entry.startswith("sc-domain:"):
            dom = entry.split(":", 1)[1].lower()
            if dom == host_bare or host_bare.endswith("." + dom):
                return entry

    # 2) URL-prefix exacte
    for entry in entries:
        parsed = urlparse(entry)
        entry_host = parsed.netloc.lower()
        if entry_host in (host, host_bare, "www." + host_bare):
            return entry

    return site_url


def fetch_search_analytics(
    project_slug: str,
    site_url: str,
    start_date: str,
    end_date: str,
    search_type: str = "discover",
    row_limit: int = GSC_MAX_TOTAL_ROWS,
) -> list[dict[str, Any]]:
    """Récupère les pages avec trafic pour une période + type.

    search_type :
      - "discover"  → Google Discover (notre cas principal)
      - "web"       → résultats de recherche classiques
      - "googleNews"→ Google Actualités

    Pagination automatique (GSC limite à 25k lignes par requête).
    """
    access_token = get_valid_access_token(project_slug)
    encoded_url = quote(site_url, safe="")
    api_url = f"{GSC_API_BASE}/sites/{encoded_url}/searchAnalytics/query"

    all_rows: list[dict[str, Any]] = []
    start_row = 0
    while True:
        remaining = row_limit - len(all_rows)
        if remaining <= 0:
            break
        page_size = min(GSC_MAX_ROWS_PER_CALL, remaining)

        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["page"],
            "type": search_type,
            "rowLimit": page_size,
            "startRow": start_row,
        }
        response = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=body,
            timeout=TIMEOUT_S,
        )
        if response.status_code >= 400:
            try:
                err = response.json().get("error", {}).get("message", response.text)
            except (json.JSONDecodeError, ValueError):
                err = response.text
            raise RuntimeError(
                f"Erreur API GSC ({response.status_code}): {err}"
            )

        rows = response.json().get("rows", [])
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        start_row += page_size

    result: list[dict[str, Any]] = []
    for row in all_rows:
        keys = row.get("keys", [])
        url = keys[0] if keys else ""
        if not url:
            continue
        result.append(
            {
                "url": url,
                "clicks": int(row.get("clicks", 0)),
                "impressions": int(row.get("impressions", 0)),
                "ctr": round(float(row.get("ctr", 0)) * 100, 2),
            }
        )

    result.sort(key=lambda r: r["clicks"], reverse=True)
    return result


# ============================================================
# Helpers haut niveau
# ============================================================


def fetch_discover_12m(
    project_slug: str,
    site_url: str,
    days: int = 365,
) -> dict[str, Any]:
    """Récupère les pages avec trafic Discover sur les N derniers jours."""
    resolved = resolve_site_url(project_slug, site_url)
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)

    rows = fetch_search_analytics(
        project_slug,
        resolved,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        search_type="discover",
    )

    return {
        "project": project_slug,
        "site_url": resolved,
        "search_type": "discover",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "fetched_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(rows),
        "rows": rows,
    }
