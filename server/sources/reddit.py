"""Reddit fetcher : top posts /r/france + subs thématiques.

DEUX MODES selon les credentials disponibles :

  1. **OAuth (script app)** — si REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET
     sont configurés. Marche partout (y compris IPs cloud / GitHub
     Actions). Récupère score, num_comments, upvote_ratio.

  2. **RSS public** (fallback) — sans credentials. Marche en local
     depuis IP résidentielle, MAIS Reddit blackliste les IPs datacenter
     (CI cloud) et renvoie alors un Atom vide sans erreur explicite.
     Pas de score/upvotes (RSS Atom les expose pas).

Reddit est un **anticipateur** clé pour Discover : Google indexe les
posts/comments, et un pic de présence sur Reddit précède souvent
(12-48h) le pic Discover sur les sites éditoriaux français.

Couverture : /r/france (généraliste) + subs thématiques majeurs FR
(politique, sciences, tech, jeux vidéo, cinéma, cuisine).

Format de retour :
  - posts[] avec title, url, subreddit, rank_in_sub, permalink,
    published_at, domain, author + (mode OAuth) score, num_comments,
    upvote_ratio
  - Dédupliqués par URL externe avec compteur cross_subs
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

import requests

from server.config import settings
from server.sources._common import now_iso, today_str, write_snapshot

TIMEOUT_S = 12
SOURCE_KEY = "reddit"
SLEEP_BETWEEN_SUBS_S = 0.3
RSS_NS = {
    "atom": "http://www.w3.org/2005/Atom",
}

# Subs ciblés : généraliste + thématiques majeures FR.
# Si un sub n'existe pas / est privé, le RSS retourne 404 → ignoré
# silencieusement par fetch().
SUBS: list[str] = [
    "france",            # généraliste FR (le + gros)
    "actualite",         # news FR
    "francepolitique",   # politique
    "sciences",          # sciences (anglo)
    "Histoire",          # histoire FR
    "technologie",       # tech FR
    "jeuxvideo",         # gaming FR
    "cinema_francais",   # ciné FR
    "musique",           # musique
    "Cuisine",           # food FR
    "AskFrance",         # questions société FR
    "europe",            # contexte EU (FR-friendly)
]

# UA descriptif (best practice Reddit même sur RSS).
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 EditorialSignal/1.0 "
        "(+https://newsroom-blush.vercel.app)"
    ),
    "Accept": "application/atom+xml,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}

# Extrait l'URL externe depuis la description HTML (contient
# `<a href="...">[link]</a>` qui pointe vers l'article original).
_EXT_LINK_RE = re.compile(
    r'<a\s+href="(?P<url>https?://[^"]+)"[^>]*>\s*\[link\]\s*</a>',
    re.IGNORECASE,
)


def _parse_atom(xml_text: str, sub: str) -> list[dict[str, Any]]:
    """Parse le flux Atom Reddit et retourne une liste de posts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    out: list[dict[str, Any]] = []
    entries = root.findall("atom:entry", RSS_NS)
    for rank, entry in enumerate(entries, start=1):
        title_el = entry.find("atom:title", RSS_NS)
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            continue

        # link primaire = permalink Reddit
        link_el = entry.find("atom:link", RSS_NS)
        permalink = link_el.get("href", "") if link_el is not None else ""

        # author = u/xxx
        author_el = entry.find("atom:author/atom:name", RSS_NS)
        author = (author_el.text or "").strip() if author_el is not None else ""

        # published timestamp
        pub_el = entry.find("atom:published", RSS_NS)
        published_at = (pub_el.text or "").strip() if pub_el is not None else ""

        # content HTML : on en extrait l'URL externe si présente
        content_el = entry.find("atom:content", RSS_NS)
        content_html = (content_el.text or "") if content_el is not None else ""
        ext_match = _EXT_LINK_RE.search(content_html)
        external_url = ext_match.group("url") if ext_match else ""

        # Si l'URL externe = permalink, c'est un self-post (texte) →
        # on garde l'URL Reddit comme URL "primaire" mais flag is_self.
        is_self = (
            not external_url
            or external_url.startswith("https://www.reddit.com/")
            or external_url.startswith("https://old.reddit.com/")
        )
        primary_url = permalink if is_self else external_url

        domain = ""
        if external_url and not is_self:
            try:
                domain = urlparse(external_url).netloc.replace("www.", "")
            except Exception:  # noqa: BLE001
                domain = ""

        out.append(
            {
                "title": title,
                "url": primary_url,
                "external_url": external_url,
                "permalink": permalink,
                "subreddit": sub,
                "rank_in_sub": rank,
                "published_at": published_at,
                "author": author,
                "is_self": is_self,
                "domain": domain,
            }
        )
    return out


def _fetch_sub(sub: str) -> list[dict[str, Any]]:
    """Fetch le RSS d'un sub. Retourne [] si erreur/404."""
    url = f"https://www.reddit.com/r/{sub}/hot.rss"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
        if response.status_code in (403, 404):
            return []
        response.raise_for_status()
    except requests.RequestException:
        return []
    return _parse_atom(response.text, sub=sub)


# ---------------------------------------------------------------
# Mode OAuth (script app) — utilisable depuis n'importe quelle IP
# ---------------------------------------------------------------


def _get_oauth_token() -> tuple[str | None, str]:
    """Récupère un access_token via client_credentials.

    Retourne (token, reason). reason explique pourquoi None est retourné,
    affiché dans le snapshot pour diagnostiquer en CI.
    """
    if not settings.reddit_client_id:
        return None, "no_client_id"
    if not settings.reddit_client_secret:
        return None, "no_client_secret"
    try:
        r = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": settings.reddit_user_agent},
            timeout=TIMEOUT_S,
        )
        if r.status_code != 200:
            body = r.text[:120] if r.text else ""
            return None, f"http_{r.status_code}: {body}"
        token = r.json().get("access_token")
        if not token:
            return None, "no_token_in_response"
        return token, "ok"
    except requests.RequestException as exc:
        return None, f"request_error: {type(exc).__name__}"
    except ValueError as exc:
        return None, f"json_error: {exc}"


def _fetch_sub_oauth(sub: str, token: str) -> list[dict[str, Any]]:
    """Fetch les posts 'hot' d'un sub via OAuth. Plus riche que le RSS
    (score, num_comments, upvote_ratio, domain extrait)."""
    url = f"https://oauth.reddit.com/r/{sub}/hot.json?limit=25"
    try:
        r = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": settings.reddit_user_agent,
            },
            timeout=TIMEOUT_S,
        )
        if r.status_code in (403, 404):
            return []
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError):
        return []

    out: list[dict[str, Any]] = []
    children = payload.get("data", {}).get("children", [])
    for rank, child in enumerate(children, start=1):
        data = child.get("data") or {}
        if data.get("stickied"):
            continue
        title = (data.get("title") or "").strip()
        if not title:
            continue
        external_url = (
            data.get("url_overridden_by_dest") or data.get("url") or ""
        ).strip()
        permalink_path = data.get("permalink") or ""
        permalink = f"https://www.reddit.com{permalink_path}" if permalink_path else ""

        is_self = bool(data.get("is_self")) or (
            external_url.startswith("https://www.reddit.com/")
            or external_url.startswith("https://old.reddit.com/")
        )
        primary_url = permalink if is_self else (external_url or permalink)

        out.append(
            {
                "title": title,
                "url": primary_url,
                "external_url": external_url,
                "permalink": permalink,
                "subreddit": sub,
                "rank_in_sub": rank,
                "published_at": "",  # Pas dans la réponse OAuth de base
                "author": data.get("author") or "",
                "is_self": is_self,
                "domain": (data.get("domain") or "").replace("self.", ""),
                # Données enrichies vs RSS :
                "score": int(data.get("score") or 0),
                "num_comments": int(data.get("num_comments") or 0),
                "upvote_ratio": float(data.get("upvote_ratio") or 0),
            }
        )
    return out


def fetch() -> dict[str, Any]:
    """Fetch tous les subs, dédup par URL, compte la viralité cross-sub.

    Choisit le mode OAuth si REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET
    sont définis (requis pour CI où Reddit blackliste les IPs cloud),
    sinon fallback sur RSS public.
    """
    oauth_token, oauth_reason = _get_oauth_token()
    mode = "oauth" if oauth_token else "rss"
    print(f"[reddit] mode={mode} oauth_status={oauth_reason}")

    all_posts: list[dict[str, Any]] = []
    counts_by_sub: dict[str, int] = {}
    failures: list[dict[str, str]] = []

    for sub in SUBS:
        try:
            if oauth_token:
                posts = _fetch_sub_oauth(sub, oauth_token)
            else:
                posts = _fetch_sub(sub)
        except Exception as exc:  # noqa: BLE001
            failures.append({"sub": sub, "error": f"{type(exc).__name__}: {exc}"})
            counts_by_sub[sub] = 0
            continue
        counts_by_sub[sub] = len(posts)
        all_posts.extend(posts)
        time.sleep(SLEEP_BETWEEN_SUBS_S)

    # Dédup par URL en agrégeant les présences cross-sub. Un même article
    # posté dans /r/france ET /r/actualite est un signal de viralité fort
    # (équivalent au gnews_count pour Google News).
    by_url: dict[str, dict[str, Any]] = {}
    for post in all_posts:
        key = post["url"]
        if not key:
            continue
        existing = by_url.get(key)
        if existing is None:
            post_copy = dict(post)
            post_copy["cross_subs"] = [post["subreddit"]]
            post_copy["cross_subs_count"] = 1
            # On garde le meilleur (= plus petit) rank parmi les subs
            post_copy["best_rank"] = post["rank_in_sub"]
            by_url[key] = post_copy
        else:
            if post["subreddit"] not in existing["cross_subs"]:
                existing["cross_subs"].append(post["subreddit"])
                existing["cross_subs_count"] += 1
            if post["rank_in_sub"] < existing["best_rank"]:
                existing["best_rank"] = post["rank_in_sub"]

    deduped = list(by_url.values())
    # Tri : d'abord par viralité cross-sub, puis par rank dans le feed
    # (plus petit rank = plus chaud).
    deduped.sort(key=lambda p: (-p["cross_subs_count"], p["best_rank"]))

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "mode": mode,
        "oauth_status": oauth_reason,  # ok / no_client_id / http_401 / ...
        "subs": SUBS,
        "counts_by_sub": counts_by_sub,
        "failures": failures,
        "count": len(deduped),
        "posts": deduped,
    }


def run() -> dict[str, Any]:
    payload = fetch()
    write_snapshot(SOURCE_KEY, payload, today_str())
    return payload
