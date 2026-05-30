"""Décode les URLs Google News (`news.google.com/rss/articles/CBMi...`)
vers l'URL réelle du publisher (lemonde.fr, bfmtv.com, etc.).

Depuis 2024, Google News n'expose plus l'URL en clair dans le path
base64 : il faut appeler leur endpoint interne `batchexecute` avec un
token de signature pour récupérer l'URL d'origine.

Flow :
  1. Récupère le base64 du path (`CBMi...`)
  2. GET https://news.google.com/articles/<base64> pour récupérer
     les data-n-a-id et data-n-a-sg dans le HTML
  3. POST batchexecute avec ces tokens → JSON contenant l'URL réelle

Cache local : data/gnews_url_cache.json (clé = hash de l'URL Google
News). Évite de re-décoder à chaque run du pipeline.

Tolérant aux échecs : si une URL échoue (HTML cassé, rate limit, etc.)
on retourne l'URL Google News originale, le pipeline continue.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from server.config import DATA_DIR
from server.sources._common import now_iso

CACHE_PATH = DATA_DIR / "gnews_url_cache.json"
TIMEOUT_S = 12
SLEEP_BETWEEN_S = 1.0  # politesse — Google rate-limit en 429 si trop rapide
BATCHEXECUTE_URL = (
    "https://news.google.com/_/DotsSplashUi/data/batchexecute"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}


def _new_session() -> requests.Session:
    """Session pré-configurée avec cookies consent Google (bypass RGPD).

    Sans ces cookies, Google News redirige vers consent.google.com et le
    HTML ne contient pas les tokens nécessaires au décodage.
    """
    s = requests.Session()
    s.cookies.set("CONSENT", "YES+cb", domain=".google.com")
    s.cookies.set(
        "SOCS", "CAESHAgBEhJnd3NfMjAyMzAxMjQtMF9SQzIaAmZyIAEaBgiAjuibBg",
        domain=".google.com",
    )
    s.headers.update(HEADERS)
    return s


# ---------------------------------------------------------------
# Cache local sur disque
# ---------------------------------------------------------------


def _load_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_cache(cache: dict[str, dict[str, Any]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _key_for(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------
# Détection format Google News
# ---------------------------------------------------------------


def is_google_news_url(url: str) -> bool:
    """True si l'URL est une URL Google News qu'il faut décoder."""
    if not url:
        return False
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return "news.google.com" in host


def _extract_b64_id(url: str) -> str | None:
    """Extrait le segment base64 après /articles/ dans une URL Google News."""
    try:
        path = urlparse(url).path
    except ValueError:
        return None
    # /rss/articles/CBMi... ou /articles/CBMi...
    m = re.search(r"/articles/([^?/]+)", path)
    return m.group(1) if m else None


# ---------------------------------------------------------------
# Appel batchexecute pour récupérer l'URL réelle
# ---------------------------------------------------------------


class RateLimitedError(Exception):
    """Google a renvoyé 429 ou nous a redirigé vers /sorry/."""


def _fetch_signature(
    session: requests.Session, b64_id: str
) -> tuple[str, str, str] | None:
    """GET la page article, extrait (id, timestamp, signature).

    Raise RateLimitedError si Google nous bloque (429 ou redirect vers
    /sorry/). On distingue ça d'un vrai échec pour pouvoir retenter au
    prochain run sans polluer le cache d'échecs définitifs.
    """
    article_url = f"https://news.google.com/articles/{b64_id}"
    try:
        r = session.get(article_url, timeout=TIMEOUT_S)
    except requests.RequestException:
        return None

    # Rate limit / sorry page
    if r.status_code == 429 or "/sorry/" in r.url:
        raise RateLimitedError(f"Google rate-limit ({r.status_code})")
    if r.status_code != 200:
        return None

    html = r.text
    m_id = re.search(r'data-n-a-id="([^"]+)"', html)
    m_ts = re.search(r'data-n-a-ts="([^"]+)"', html)
    m_sg = re.search(r'data-n-a-sg="([^"]+)"', html)
    if not (m_id and m_ts and m_sg):
        return None
    return m_id.group(1), m_ts.group(1), m_sg.group(1)


def _call_batchexecute(
    session: requests.Session,
    b64_id: str,
    n_a_id: str,
    n_a_ts: str,
    n_a_sg: str,
) -> str | None:
    """POST batchexecute Fbv4je avec les tokens → retourne l'URL réelle.

    Format reverse-engineeré depuis 2024 :
    - rpcid = "Fbv4je" (garturlreq = "get article url request")
    - data = [params, b64_id, timestamp, signature]
    - response = ")]}'\\n<n>\\n[[wrb.fr,Fbv4je,\\"[\\\\\\"http://...\\\\\\",...]\\"...]]"
    """
    inner = [
        "Fbv4je",
        json.dumps(
            [
                "garturlreq",
                [
                    [
                        "X", "X", ["X", "X"], None, None, 1, 1,
                        "US:en", None, 1, None, None, None, None, None, 0, 1,
                    ],
                    "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0,
                ],
                b64_id,
                int(n_a_ts),
                n_a_sg,
            ],
            separators=(",", ":"),
        ),
    ]
    f_req = json.dumps([[inner]], separators=(",", ":"))

    try:
        r = session.post(
            BATCHEXECUTE_URL,
            data={"f.req": f_req},
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            },
            timeout=TIMEOUT_S,
        )
        if r.status_code != 200:
            return None
        text = r.text
    except requests.RequestException:
        return None

    # La 1ère URL http(s) qui n'est pas un domaine Google
    for m in re.finditer(r'https?:\\?/\\?/[^",\\\s\]]+', text):
        candidate = (
            m.group(0)
            .replace("\\/", "/")
            .replace("\\u003d", "=")
            .replace("\\u0026", "&")
        )
        try:
            host = urlparse(candidate).hostname or ""
        except ValueError:
            continue
        if (
            host
            and "google.com" not in host
            and "gstatic.com" not in host
            and "googleapis.com" not in host
            and "schema.org" not in host
        ):
            return candidate
    return None


def decode_url(google_news_url: str, *, use_cache: bool = True) -> str:
    """Décode une URL Google News vers l'URL réelle du publisher.

    Retourne l'URL d'origine si le décodage échoue (tolérant).
    """
    if not is_google_news_url(google_news_url):
        return google_news_url

    cache = _load_cache() if use_cache else {}
    key = _key_for(google_news_url)
    if use_cache and key in cache and cache[key].get("real_url"):
        return cache[key]["real_url"]

    b64_id = _extract_b64_id(google_news_url)
    if not b64_id:
        return google_news_url

    session = _new_session()
    try:
        signature = _fetch_signature(session, b64_id)
    except RateLimitedError:
        # On NE cache pas : on retentera au prochain run
        return google_news_url

    if not signature:
        # Vrai échec (HTML changé, pas de tokens) → on cache pour ne pas
        # retenter à chaque run
        cache[key] = {
            "google_url": google_news_url,
            "real_url": None,
            "decoded_at": now_iso(),
            "error": "no_signature",
        }
        _save_cache(cache)
        return google_news_url

    real_url = _call_batchexecute(session, b64_id, *signature)
    cache[key] = {
        "google_url": google_news_url,
        "real_url": real_url,
        "decoded_at": now_iso(),
    }
    _save_cache(cache)
    return real_url or google_news_url


def decode_many(
    urls: list[str],
    *,
    sleep_s: float = SLEEP_BETWEEN_S,
    on_progress=None,
) -> dict[str, str]:
    """Décode une liste d'URLs avec politesse. Retourne {url_google: url_real}.

    Les URLs déjà en cache sont résolues instantanément (pas de sleep).
    """
    out: dict[str, str] = {}
    cache = _load_cache()
    n_to_fetch = sum(
        1
        for u in urls
        if is_google_news_url(u) and _key_for(u) not in cache
    )
    fetched = 0
    for i, url in enumerate(urls):
        if not is_google_news_url(url):
            out[url] = url
            continue
        key = _key_for(url)
        if key in cache and cache[key].get("real_url"):
            out[url] = cache[key]["real_url"]
            continue
        out[url] = decode_url(url)
        fetched += 1
        if on_progress:
            on_progress(fetched, n_to_fetch)
        time.sleep(sleep_s)
    return out
