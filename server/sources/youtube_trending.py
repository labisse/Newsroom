"""YouTube Trending FR — pool elargi + classification editoriale.

V2 (mai 2026) : on ne fait plus un seul `chart=mostPopular`. On
interroge plusieurs `videoCategoryId` cles pour ramener un pool plus
representatif (250-300 videos vs 50). Puis on **reclassifie** chaque
video via une cascade :

  1. categorie YouTube brute (categoryId)  -> categorie canonique
  2. si la chaine est dans EDITORIAL_CHANNELS_FR (BFM, Brut, Konbini,
     HugoDecrypte, ScienceEtonnante, L'Equipe...) -> override avec
     la categorie de la chaine + flag is_editorial=True
  3. detection de mots-cles FR dans title + tags + description :
     - sur les categoryId generiques (Entertainment, People), un seul
       hit suffit pour reclassifier
     - sur les categoryId specifiques (News, Sport), il faut >= 2 hits
       et la categorie detectee doit avoir un meilleur score

Sortie : champ `editorial_category` canonique (compatible avec la grille
10 categories de evolution/categories) + `is_editorial: bool` +
`category_label` (FR humain, retrocompat).

Cout API : 6 calls/run x 4 runs/jour = 24 unites/jour (quota 10 000).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import requests

from server.config import settings
from server.sources._common import now_iso, today_str, write_snapshot

TIMEOUT_S = 15
SOURCE_KEY = "youtube_trending"
MAX_RESULTS = 50  # cap API = 50 par page

# Categories YouTube qu'on interroge separement pour densifier le pool.
# IDs : https://developers.google.com/youtube/v3/docs/videoCategories/list
EXTRA_CATEGORY_QUERIES: list[tuple[str, str]] = [
    ("25", "Actualités & politique"),
    ("17", "Sport"),
    ("28", "Sciences & tech"),
    ("24", "Divertissement"),
    ("22", "Vlogs"),
]

# Mapping pour le label humain (retrocompat front)
YT_CATEGORY_LABELS: dict[str, str] = {
    "1": "Films & animation",
    "2": "Autos & véhicules",
    "10": "Musique",
    "15": "Animaux",
    "17": "Sport",
    "19": "Voyages & événements",
    "20": "Jeux vidéo",
    "22": "Vlogs",
    "23": "Comédie",
    "24": "Divertissement",
    "25": "Actualités & politique",
    "26": "Conseils & style",
    "27": "Éducation",
    "28": "Sciences & tech",
    "29": "Associatif & engagement",
}

# Mapping YT categoryId -> categorie canonique editoriale.
# Les categories generiques (Divertissement, People, Music, Gaming, Comedy)
# tombent en "people" mais sont les premieres reclassifiees si la
# detection mot-cle remonte une vraie thematique.
YT_TO_CANONICAL: dict[str, str] = {
    "25": "politique",      # News & Politics
    "17": "sport",          # Sports
    "28": "tech",           # Science & Tech (default tech, reclassif si vrai sciences)
    "27": "science",        # Education
    "29": "societe",        # Nonprofits & Activism
    "26": "lifestyle",      # Howto & Style
    "15": "lifestyle",      # Pets & Animals
    "19": "lifestyle",      # Travel & Events
    "2": "lifestyle",       # Autos & Vehicles
    # Generiques -> people par defaut, faciles a reclassifier :
    "1": "people",          # Film & Animation
    "10": "people",         # Music
    "20": "people",         # Gaming
    "22": "people",         # People & Blogs
    "23": "people",         # Comedy
    "24": "people",         # Entertainment
}

# Categories YouTube considerees "specifiques" : on garde leur classification
# sauf si les mots-cles detectent FORTEMENT autre chose (>= 2 hits ET
# meilleur que le score actuel).
SPECIFIC_YT_CATS: set[str] = {"25", "17", "28", "27"}

# Whitelist chaines editoriales FR : channel_title (lowercased, strip)
# -> (canonical_category, editorial_type).
# editorial_type sert juste de tag descriptif pour le front futur.
EDITORIAL_CHANNELS_FR: dict[str, tuple[str, str]] = {
    # News mainstream
    "bfmtv": ("politique", "news"),
    "france 24": ("international", "news"),
    "france 24 français": ("international", "news"),
    "tf1 info": ("societe", "news"),
    "france info": ("politique", "news"),
    "franceinfo": ("politique", "news"),
    "le figaro": ("politique", "news"),
    "le monde": ("politique", "news"),
    "le monde.fr": ("politique", "news"),
    "libération": ("politique", "news"),
    "liberation": ("politique", "news"),
    "brut": ("societe", "news"),
    "brut.": ("societe", "news"),
    "konbini news": ("societe", "news"),
    "konbini": ("people", "news"),
    "hugodécrypte - actus du jour": ("politique", "news"),
    "hugodecrypte - actus du jour": ("politique", "news"),
    "hugodecrypte": ("politique", "news"),
    "blast, le souffle de l'info": ("politique", "investigation"),
    "blast": ("politique", "investigation"),
    "le média": ("politique", "investigation"),
    "le media": ("politique", "investigation"),
    "thinkerview": ("politique", "investigation"),
    "mediapart": ("politique", "investigation"),
    "rmc": ("politique", "news"),
    "europe 1": ("politique", "news"),
    "rfi": ("international", "news"),
    "arte": ("societe", "news"),
    "arte tv": ("societe", "news"),
    "france 2": ("politique", "news"),
    "france 3": ("societe", "news"),
    "france inter": ("politique", "news"),
    "france culture": ("societe", "news"),
    "tv5monde info": ("international", "news"),
    "ina actu": ("societe", "news"),
    # Sciences
    "scienceetonnante": ("science", "sciences"),
    "science étonnante": ("science", "sciences"),
    "dr nozman": ("science", "sciences"),
    "drnozman": ("science", "sciences"),
    "dirty biology": ("science", "sciences"),
    "le réveilleur": ("science", "sciences"),
    "le reveilleur": ("science", "sciences"),
    "balade mentale": ("science", "sciences"),
    "string theory fr": ("science", "sciences"),
    "doc seven": ("science", "sciences"),
    "le vortex": ("science", "sciences"),
    "astronogeek": ("science", "sciences"),
    "e-penser": ("science", "sciences"),
    "epenser": ("science", "sciences"),
    "fouloscopie": ("science", "sciences"),
    "passe-science": ("science", "sciences"),
    "monsieur phi": ("science", "sciences"),
    "monsieur bidouille": ("tech", "sciences"),
    "experimentboy": ("science", "sciences"),
    # Sport
    "l'équipe": ("sport", "sports"),
    "l equipe": ("sport", "sports"),
    "lequipe": ("sport", "sports"),
    "téléfoot - la chaîne": ("sport", "sports"),
    "telefoot - la chaine": ("sport", "sports"),
    "eurosport france": ("sport", "sports"),
    "rmc sport": ("sport", "sports"),
    "canal+ sport": ("sport", "sports"),
    "canal plus sport": ("sport", "sports"),
    # Tech
    "micode": ("tech", "tech"),
    "underscore_": ("tech", "tech"),
    "underscore": ("tech", "tech"),
    "cocadmin": ("tech", "tech"),
    "next inpact": ("tech", "tech"),
    "presse-citron": ("tech", "tech"),
    "presse citron": ("tech", "tech"),
    "frandroid": ("tech", "tech"),
    "01net": ("tech", "tech"),
    "jvtv": ("tech", "tech"),
    # Sante
    "doctissimo": ("sante", "health"),
    "santé+ magazine": ("sante", "health"),
    "sante+ magazine": ("sante", "health"),
    # Economie
    "xerfi canal": ("economie", "economy"),
    "heureka": ("economie", "economy"),
    "heu?reka": ("economie", "economy"),
    "économiquement votre": ("economie", "economy"),
    # International (chaines etrangeres pertinentes FR)
    "euronews (en français)": ("international", "news"),
    "euronews francais": ("international", "news"),
}

# Lexiques de mots-cles par categorie canonique. Pattern regex teste sur
# title + tags + description (case-insensitive, word boundaries).
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "politique": [
        r"\bmacron\b", r"\bélys[ée]e\b", r"\bgouvernement\b", r"\bministre\b",
        r"\bélection", r"\bparlement\b", r"\bassembl[ée]e nationale\b",
        r"\bdéput[ée]\b", r"\bsénat\b", r"\bmélenchon\b", r"\ble pen\b",
        r"\brassemblement national\b", r"\b(lfi|nupes|nfp)\b", r"\bprésident\b",
        r"\bpremier ministre\b", r"\bréforme\b", r"\blois?\b", r"\bdécret\b",
        r"\bcongr[ée]s\b",
    ],
    "international": [
        # Note : on evite les patterns trop courts/ambigus (usa, europe)
        # qui matchent des hashtags opportunistes (#usa, #europe) hors
        # contexte news. On garde les noms propres et termes specifiques.
        r"\bukraine\b", r"\brussie\b", r"\bpoutine\b", r"\btrump\b",
        r"\bétats[- ]unis\b", r"\bchine\b", r"\bisra[ée]l\b",
        r"\bgaza\b", r"\bhamas\b", r"\biran\b", r"\bonu\b",
        r"\bunion européenne\b", r"\b(otan|nato)\b",
        r"\bafrique\b", r"\bbiden\b", r"\bzelensky\b", r"\bnetanyahou\b",
        r"\bmoyen[- ]orient\b", r"\bdiplomati(e|que)\b",
    ],
    "economie": [
        r"\béconomie\b", r"\bbourse\b", r"\binflation\b", r"\bbce\b",
        r"\bbanque centrale\b", r"\bcrise économique\b", r"\bch[oô]mage\b",
        r"\bsalaire\b", r"\bretraite\b", r"\bpouvoir d'achat\b", r"\bdette\b",
        r"\bbudget\b", r"\béco\b", r"\bcac.?40\b", r"\bfinance\b",
        r"\bimm?obilier\b", r"\btaxe\b", r"\bimp[ôo]ts?\b",
    ],
    "tech": [
        r"\b(ia|i\.a\.)\b", r"\bintelligence artificielle\b", r"\bchatgpt\b",
        r"\bopenai\b", r"\banthropic\b", r"\biphone\b", r"\bandroid\b",
        r"\btesla\b", r"\bspacex\b", r"\belon musk\b", r"\bcyber",
        r"\bsmartphone\b", r"\bordinateur\b", r"\bdéveloppe(?:ur|ment)\b",
        r"\bcode\b", r"\bgafam\b", r"\bsilicon valley\b", r"\bvr\b",
        r"\bréalité virtuelle\b", r"\bblockchain\b", r"\bbitcoin\b",
        r"\bcrypto\b",
    ],
    "sport": [
        r"\bfoot(ball)?\b", r"\bpsg\b", r"\bom\b", r"\bmarseille\b",
        r"\bbasket\b", r"\bnba\b", r"\btennis\b", r"\broland.?garros\b",
        r"\brugby\b", r"\bxv de france\b", r"\bjeux olympiques\b",
        r"\bjo paris\b", r"\bmbapp[ée]\b", r"\bzidane\b", r"\bligue 1\b",
        r"\bligue des champions\b", r"\b(f1|formule 1)\b", r"\bgrand prix\b",
        r"\bsport\b", r"\bmatch\b", r"\btournoi\b", r"\bcoupe du monde\b",
        r"\beuro\b",
    ],
    "science": [
        r"\bétude\b", r"\brecherche scientifique\b", r"\bscientifique\b",
        r"\bcosmos\b", r"\bespace\b", r"\bplanète\b", r"\bnasa\b", r"\besa\b",
        r"\bphysique\b", r"\bchimie\b", r"\bbiologie\b", r"\bgénétique\b",
        r"\barchéologie\b", r"\bclimat\b", r"\bréchauffement\b", r"\bgalaxie\b",
        r"\btrou noir\b", r"\bquantique\b",
        # "évolution" retire : trop ambigu (matche "évolution du PSG", etc)
    ],
    "sante": [
        r"\bsanté\b", r"\bcovid\b", r"\bvirus\b", r"\bvaccin\b", r"\bhôpital\b",
        r"\bmédecin\b", r"\bmaladie\b", r"\bcancer\b", r"\balzheimer\b",
        r"\bnutrition\b", r"\bdiabète\b", r"\bpharmacie\b", r"\bgrippe\b",
        r"\bépidémie\b", r"\bpandémie\b", r"\bdépression\b",
    ],
    "people": [
        r"\binfluenc(eur|euse)\b", r"\bcélébrité\b", r"\bvlog\b", r"\bteam\b",
        r"\binstagram\b", r"\btiktok\b", r"\binterview\b", r"\binvité[e]?\b",
        r"\bémission\b", r"\béclats?\b", r"\bbuzz\b", r"\bcouple\b",
        r"\brupture\b", r"\bmariage\b",
    ],
    "societe": [
        r"\bsociété\b", r"\bfait[s]? divers\b", r"\bjustice\b", r"\btribunal\b",
        r"\bpolice\b", r"\bgendarmerie\b", r"\bmanifestation\b",
        r"\béducation\b", r"\b[ée]cole\b", r"\buniversit[ée]\b", r"\bbac\b",
        r"\bféminisme\b", r"\bracisme\b", r"\bdiscrimination\b",
        r"\bbanlieue\b", r"\bémeute\b", r"\binsécurité\b",
    ],
    "lifestyle": [
        r"\bcuisine\b", r"\brecette\b", r"\bvoyage\b", r"\bmode\b",
        r"\bbeauté\b", r"\bdécoration\b", r"\bjardinage\b", r"\bbricolage\b",
        r"\bfitness\b", r"\byoga\b", r"\bvegan\b", r"\bdiy\b",
        r"\b(restaurant|gastronomie)\b",
    ],
}

# Pre-compile les regex (run 4x/jour avec ~300 videos).
_COMPILED_KEYWORDS: dict[str, list[re.Pattern[str]]] = {
    cat: [re.compile(p, re.IGNORECASE) for p in patterns]
    for cat, patterns in CATEGORY_KEYWORDS.items()
}


def _parse_iso8601_duration(duration: str) -> int:
    """PT4M13S -> 253 (secondes). PT1H2M30S -> 3750."""
    if not duration:
        return 0
    pattern = re.compile(
        r"PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?"
    )
    match = pattern.match(duration)
    if not match:
        return 0
    h = int(match.group("h") or 0)
    m = int(match.group("m") or 0)
    s = int(match.group("s") or 0)
    return h * 3600 + m * 60 + s


def _hours_since(iso_ts: str) -> float:
    """Combien d'heures depuis published_at."""
    if not iso_ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    delta = datetime.now(timezone.utc) - dt
    return delta.total_seconds() / 3600.0


def _score_keywords(text: str) -> dict[str, int]:
    """Compte les hits par categorie sur un blob texte."""
    if not text:
        return {}
    scores: dict[str, int] = {}
    for cat, patterns in _COMPILED_KEYWORDS.items():
        hits = sum(1 for p in patterns if p.search(text))
        if hits:
            scores[cat] = hits
    return scores


def _classify_video(
    yt_category_id: str,
    channel_title: str,
    title: str,
    tags: list[str],
    description: str,
) -> tuple[str, bool, list[str]]:
    """Cascade de classification.

    Retourne (editorial_category, is_editorial, reasons).
    `reasons` liste les regles appliquees pour debug.
    """
    reasons: list[str] = []

    # 1. Defaut : mapping YT categoryId -> canonical
    default_cat = YT_TO_CANONICAL.get(yt_category_id, "people")
    cat = default_cat
    reasons.append(f"yt_cat={yt_category_id}->{default_cat}")
    is_editorial = False

    # 2. Override si la chaine est dans la whitelist
    chan_key = (channel_title or "").lower().strip()
    if chan_key in EDITORIAL_CHANNELS_FR:
        wl_cat, wl_type = EDITORIAL_CHANNELS_FR[chan_key]
        cat = wl_cat
        is_editorial = True
        reasons.append(f"channel_whitelist={chan_key}->{wl_cat}({wl_type})")
        # On laisse les keywords tourner pour eventuellement nuancer
        # (ex: BFM->politique par defaut, mais une video sur Israel
        # peut etre reclassifiee international)

    # 3. Mots-cles sur title + tags + description.
    # On pondere : title compte double pour reduire le bruit des hashtags
    # opportunistes dans description (ex: #usa dans une video de voiture).
    title_score = _score_keywords(title or "")
    other_score = _score_keywords(
        " ".join([" ".join(tags or []), (description or "")[:500]])
    )
    kw_scores: dict[str, int] = {}
    for c, h in title_score.items():
        kw_scores[c] = kw_scores.get(c, 0) + h * 2  # poids title x2
    for c, h in other_score.items():
        kw_scores[c] = kw_scores.get(c, 0) + h

    if kw_scores:
        top_cat = max(kw_scores, key=lambda c: kw_scores[c])
        top_hits = kw_scores[top_cat]

        # Seuil de reclassification : >= 2 hits ponderés (= 1 hit dans
        # le titre OU 2 hits ailleurs) ET strictement meilleur que le
        # score de la cat actuelle. Plus conservateur pour eviter les
        # faux positifs (hashtag opportuniste, mot isole dans desc).
        current_score = kw_scores.get(cat, 0)
        if top_hits >= 2 and top_cat != cat and top_hits > current_score:
            reasons.append(f"keywords={top_cat}({top_hits}pts) override {cat}")
            cat = top_cat

    return cat, is_editorial, reasons


def _fetch_videos_page(key: str, region: str, category_id: str | None) -> list[dict]:
    """Recupere une page de videos. Retourne [] si erreur."""
    params: dict[str, Any] = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": MAX_RESULTS,
        "key": key,
    }
    if category_id:
        params["videoCategoryId"] = category_id

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params=params,
            timeout=TIMEOUT_S,
        )
        if response.status_code != 200:
            return []
        return response.json().get("items", []) or []
    except (requests.RequestException, ValueError):
        return []


def _build_video(item: dict[str, Any]) -> dict[str, Any] | None:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    content = item.get("contentDetails") or {}

    title = (snippet.get("title") or "").strip()
    if not title:
        return None

    video_id = item.get("id") or ""
    thumbs = snippet.get("thumbnails") or {}
    thumb_url = ""
    for size in ("maxres", "high", "medium", "default"):
        tb = thumbs.get(size)
        if tb and tb.get("url"):
            thumb_url = tb["url"]
            break

    duration_s = _parse_iso8601_duration(content.get("duration") or "")
    published_at = snippet.get("publishedAt") or ""
    hours_old = _hours_since(published_at)

    views = int(stats.get("viewCount") or 0)
    velocity = views / hours_old if hours_old > 0.5 else views

    yt_cat_id = snippet.get("categoryId") or ""
    channel_title = snippet.get("channelTitle") or ""
    tags = snippet.get("tags") or []
    description = snippet.get("description") or ""

    editorial_cat, is_editorial, reasons = _classify_video(
        yt_category_id=yt_cat_id,
        channel_title=channel_title,
        title=title,
        tags=tags,
        description=description,
    )

    return {
        "id": video_id,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "channel": channel_title,
        "channel_id": snippet.get("channelId") or "",
        "description": description[:300],
        "category_id": yt_cat_id,
        "category_label": YT_CATEGORY_LABELS.get(yt_cat_id, "Autre"),  # retrocompat
        "editorial_category": editorial_cat,  # politique, sport, tech, science...
        "is_editorial": is_editorial,
        "classification_reasons": reasons,
        "tags": tags,
        "published_at": published_at,
        "hours_old": round(hours_old, 1),
        "views": views,
        "likes": int(stats.get("likeCount") or 0),
        "comments": int(stats.get("commentCount") or 0),
        "duration_s": duration_s,
        "velocity_views_per_hour": int(velocity),
        "thumbnail": thumb_url,
    }


def fetch(api_key: str | None = None, region: str | None = None) -> dict[str, Any]:
    """Recupere les videos en trending FR (pool elargi multi-categories).

    Strategie : 1 appel mostPopular global + 5 appels par categoryId
    (News, Sport, Sciences, Entertainment, People). Dedup par video_id.
    Tri final par velocity (vues/h).
    """
    key = api_key or settings.youtube_api_key
    reg = (region or settings.youtube_region or "FR").upper()

    if not key:
        return {
            "source": SOURCE_KEY,
            "fetched_at": now_iso(),
            "region": reg,
            "count": 0,
            "videos": [],
            "fetches": 0,
            "failures": [
                {
                    "reason": "missing_api_key",
                    "hint": "Set YOUTUBE_API_KEY in .env (Google Cloud Console)",
                }
            ],
        }

    # Pages a fetch : global + 1 par categorie editoriale clef
    fetch_plan: list[tuple[str | None, str]] = [(None, "mostPopular")]
    fetch_plan.extend([(cid, label) for cid, label in EXTRA_CATEGORY_QUERIES])

    all_items: dict[str, dict[str, Any]] = {}
    fetches_ok = 0
    failures: list[dict[str, str]] = []
    per_page_counts: dict[str, int] = {}

    for cat_id, label in fetch_plan:
        items = _fetch_videos_page(key, reg, cat_id)
        if not items:
            failures.append(
                {
                    "page": label,
                    "category_id": cat_id or "",
                    "reason": "no_items_or_error",
                }
            )
            per_page_counts[label] = 0
            continue
        fetches_ok += 1
        per_page_counts[label] = len(items)
        for item in items:
            vid_id = item.get("id") or ""
            if not vid_id or vid_id in all_items:
                continue
            all_items[vid_id] = item

    videos: list[dict[str, Any]] = []
    for item in all_items.values():
        built = _build_video(item)
        if built:
            videos.append(built)

    # Tri par velocity decroissante
    videos.sort(key=lambda v: v["velocity_views_per_hour"], reverse=True)

    # Stats observabilite
    editorial_count = sum(1 for v in videos if v["is_editorial"])
    by_edit_cat: dict[str, int] = {}
    for v in videos:
        by_edit_cat[v["editorial_category"]] = (
            by_edit_cat.get(v["editorial_category"], 0) + 1
        )

    return {
        "source": SOURCE_KEY,
        "fetched_at": now_iso(),
        "region": reg,
        "count": len(videos),
        "fetches": fetches_ok,
        "per_page_counts": per_page_counts,
        "editorial_count": editorial_count,
        "by_editorial_category": by_edit_cat,
        "videos": videos,
        "failures": failures,
    }


def run() -> dict[str, Any]:
    payload = fetch()
    write_snapshot(SOURCE_KEY, payload, today_str())
    return payload
