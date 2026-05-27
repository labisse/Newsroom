"""Clustering éditorial — agrégation par catégorie et par entité.

À partir des articles Discover (data/discoversnoop/latest.json), on
calcule deux vues complémentaires de la HP :

  1. categories_trending : quelles catégories Discover performent ?
     → ligne éditoriale du jour, "où aller chercher des sujets"
  2. entities_trending : quelles entités nommées reviennent ?
     → topics chauds à creuser sans qu'un article spécifique sorte

Différent du scoring article-par-article : ici on regarde le **niveau
univers** pour driver les rédacteurs avant qu'un sujet précis émerge.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

# ---------------------------------------------------------------
# Mapping catégories Discover (EN hiérarchique) → libellé FR
# Format Discover : "/Arts & Entertainment/Celebrities & Entertainment News"
# On mappe en priorité le path complet, sinon fallback sur le dernier segment.
# ---------------------------------------------------------------

CATEGORY_FR: dict[str, str] = {
    # Actualité
    "/News": "Actualité générale",
    "/News/Weather": "Météo",
    "/News/Politics": "Politique",
    "/News/Sports News": "Actualité sport",
    "/News/Health News": "Actualité santé",
    "/News/Business News": "Actualité éco",
    "/News/Local News": "Actualité locale",
    "/News/World News": "International",
    # Arts & divertissement
    "/Arts & Entertainment": "Culture & Divertissement",
    "/Arts & Entertainment/Celebrities & Entertainment News": "People",
    "/Arts & Entertainment/TV & Video": "Télévision",
    "/Arts & Entertainment/TV & Video/TV Shows & Programs": "Émissions TV",
    "/Arts & Entertainment/Movies": "Cinéma",
    "/Arts & Entertainment/Music & Audio": "Musique",
    "/Arts & Entertainment/Events & Listings": "Événements",
    "/Arts & Entertainment/Events & Listings/Concerts & Music Festivals": "Concerts & Festivals",
    "/Arts & Entertainment/Visual Art & Design": "Arts visuels",
    "/Arts & Entertainment/Performing Arts": "Spectacle vivant",
    "/Arts & Entertainment/Comics & Animation": "BD & Animation",
    "/Arts & Entertainment/Online Media": "Médias en ligne",
    # Sport
    "/Sports": "Sport",
    "/Sports/Team Sports": "Sports collectifs",
    "/Sports/Team Sports/Soccer": "Football",
    "/Sports/Team Sports/Basketball": "Basketball",
    "/Sports/Team Sports/American Football": "Football américain",
    "/Sports/Team Sports/Rugby": "Rugby",
    "/Sports/Individual Sports": "Sports individuels",
    "/Sports/Individual Sports/Racquet Sports": "Sports de raquette",
    "/Sports/Individual Sports/Cycling": "Cyclisme",
    "/Sports/Individual Sports/Golf": "Golf",
    "/Sports/Individual Sports/Track & Field": "Athlétisme",
    "/Sports/Individual Sports/Combat Sports": "Sports de combat",
    "/Sports/Motor Sports": "Sport automobile",
    "/Sports/Winter Sports": "Sports d'hiver",
    "/Sports/Water Sports": "Sports nautiques",
    # Affaires & finance
    "/Business & Industrial": "Affaires & Industrie",
    "/Business & Industrial/Energy & Utilities": "Énergie & Services publics",
    "/Finance": "Finance",
    "/Finance/Investing": "Investissement",
    "/Finance/Banking": "Banque",
    "/Finance/Insurance": "Assurance",
    # Tech
    "/Computers & Electronics": "Tech & Électronique",
    "/Computers & Electronics/Consumer Electronics": "Produits high-tech",
    "/Computers & Electronics/Software": "Logiciels",
    "/Computers & Electronics/Networking": "Réseaux",
    "/Internet & Telecom": "Internet & Télécom",
    # Cuisine & boissons
    "/Food & Drink": "Cuisine & Boissons",
    "/Food & Drink/Food & Grocery Retailers": "Distribution alimentaire",
    "/Food & Drink/Restaurants": "Restaurants",
    "/Food & Drink/Restaurants/Fast Food": "Fast food",
    "/Food & Drink/Cooking & Recipes": "Cuisine",
    # Santé
    "/Health": "Santé",
    "/Health/Medical Facilities & Services": "Établissements de santé",
    "/Health/Medical Literature & Resources": "Documentation médicale",
    "/Health/Mental Health": "Santé mentale",
    # Société
    "/Law & Government": "Justice & Gouvernement",
    "/Law & Government/Government": "Gouvernement",
    "/Law & Government/Legal": "Justice",
    "/Sensitive Subjects": "Sujets sensibles",
    "/People & Society": "Société",
    "/People & Society/Family & Relationships": "Famille & Relations",
    "/People & Society/Religion & Belief": "Religion & Croyances",
    # Voyage & transport
    "/Travel & Transportation": "Voyage & Transport",
    "/Travel & Transportation/Trips & Travel": "Voyages",
    "/Travel & Transportation/Public Transportation": "Transports publics",
    # Science
    "/Science": "Sciences",
    "/Science/Astronomy": "Astronomie",
    "/Science/Biological Sciences": "Biologie",
    "/Science/Ecology & Environment": "Écologie & Environnement",
    "/Science/Ecology & Environment/Climate Change & Global Warming": "Climat & Réchauffement",
    # Mode, shopping, lifestyle
    "/Beauty & Fitness": "Beauté & Forme",
    "/Shopping": "Shopping",
    "/Shopping/Apparel": "Mode",
    "/Shopping/Apparel/Children's Clothing": "Mode enfant",
    "/Home & Garden": "Maison & Jardin",
    "/Real Estate": "Immobilier",
    "/Pets & Animals": "Animaux",
    "/Autos & Vehicles": "Automobile",
    "/Autos & Vehicles/Motor Vehicles (By Type)": "Véhicules motorisés",
    "/Autos & Vehicles/Motor Vehicles (By Type)/Hybrid & Alternative Vehicles": "Véhicules hybrides & alternatifs",
    "/Games": "Jeux",
    "/Games/Computer & Video Games": "Jeux vidéo",
    # Education
    "/Jobs & Education": "Emploi & Éducation",
    "/Jobs & Education/Education": "Éducation",
    "/Jobs & Education/Jobs": "Emploi",
    # Référence / divers
    "/Reference": "Référence",
    "/Hobbies & Leisure": "Loisirs",
}

# Petite traduction du dernier segment pour les catégories non mappées
SEGMENT_FR: dict[str, str] = {
    "News": "Actualité",
    "Weather": "Météo",
    "Politics": "Politique",
    "Sports": "Sport",
    "Soccer": "Football",
    "Basketball": "Basketball",
    "Rugby": "Rugby",
    "Cycling": "Cyclisme",
    "Movies": "Cinéma",
    "Music": "Musique",
    "Television": "Télévision",
    "Health": "Santé",
    "Finance": "Finance",
    "Banking": "Banque",
    "Investing": "Investissement",
    "Restaurants": "Restaurants",
    "Travel": "Voyage",
    "Education": "Éducation",
    "Jobs": "Emploi",
    "Shopping": "Shopping",
    "Apparel": "Mode",
    "Astronomy": "Astronomie",
    "Government": "Gouvernement",
    "Legal": "Justice",
    "Reference": "Référence",
    "Tennis": "Tennis",
    "Golf": "Golf",
}

# Catégories trop génériques pour driver une décision éditoriale —
# on les filtre par défaut (le rédac chef sait déjà qu'il y a de "l'actu").
GENERIC_CATEGORIES: frozenset[str] = frozenset(
    {
        "/News",  # Trop large
        "",
    }
)

# Entités trop génériques pour driver une décision éditoriale.
GENERIC_ENTITIES: frozenset[str] = frozenset(
    {
        "Sport",  # 100+ occurrences sans angle précis
        "Vidéo",
        "Photo",
        "Article",
        "France",  # Présente dans tous les articles FR par construction
        "Europe",
        "Monde",
    }
)


def translate_category(category: str) -> str:
    """Traduit une catégorie Discover EN → FR, avec fallback intelligent."""
    if not category:
        return "Sans catégorie"

    # Match exact dans le mapping principal
    if category in CATEGORY_FR:
        return CATEGORY_FR[category]

    # Sinon, on prend le dernier segment et on cherche dans le mapping court
    parts = [p for p in category.strip("/").split("/") if p]
    if not parts:
        return "Sans catégorie"

    last = parts[-1]
    if last in SEGMENT_FR:
        return SEGMENT_FR[last]

    # Dernier recours : retourner le dernier segment en l'état
    return last


# ---------------------------------------------------------------
# Agrégation par catégorie
# ---------------------------------------------------------------


def cluster_by_category(
    articles: list[dict],
    *,
    min_articles: int = 3,
    min_total_score: float = 5.0,
    top_n: int = 8,
    exclude_generic: bool = True,
) -> list[dict[str, Any]]:
    """Agrège les articles Discover par catégorie.

    Retourne une liste triée par score total décroissant. Chaque entrée :
      - key         : path Discover original (clé d'identification)
      - label       : libellé FR
      - articles_count
      - total_score : somme des scores Discover (= signal de visibilité cumulée)
      - avg_score   : moyenne (= force unitaire des articles de cette catégorie)
      - top_articles: 3 meilleurs articles (par score) pour audit
    """
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for article in articles:
        cat = (article.get("category") or "").strip()
        if exclude_generic and cat in GENERIC_CATEGORIES:
            continue
        if not cat:
            continue
        by_cat[cat].append(article)

    clusters: list[dict[str, Any]] = []
    for cat, items in by_cat.items():
        if len(items) < min_articles:
            continue
        scores = [(a.get("score") or 0.0) for a in items]
        total = sum(scores)
        if total < min_total_score:
            continue

        top_articles = sorted(
            items, key=lambda a: a.get("score") or 0.0, reverse=True
        )[:3]

        clusters.append(
            {
                "key": cat,
                "label": translate_category(cat),
                "articles_count": len(items),
                "total_score": round(total, 1),
                "avg_score": round(total / len(items), 1),
                "top_articles": [
                    {
                        "title": a.get("title", ""),
                        "publisher": a.get("publisher", ""),
                        "score": round(a.get("score") or 0.0, 1),
                        "url": a.get("url", ""),
                    }
                    for a in top_articles
                ],
            }
        )

    clusters.sort(key=lambda c: c["total_score"], reverse=True)
    return clusters[:top_n]


# ---------------------------------------------------------------
# Agrégation par entité
# ---------------------------------------------------------------


def cluster_by_entity(
    articles: list[dict],
    *,
    min_articles: int = 3,
    min_total_score: float = 3.0,
    top_n: int = 15,
    exclude_generic: bool = True,
) -> list[dict[str, Any]]:
    """Agrège les articles Discover par entité nommée.

    Une entité (Pierre Deny, Canicule, Roland-Garros) peut apparaître
    dans plusieurs articles. Ce cluster donne le poids éditorial d'un
    topic indépendamment d'un article spécifique.
    """
    by_ent: dict[str, list[dict]] = defaultdict(list)
    for article in articles:
        for ent in article.get("entities_list") or []:
            ent_clean = (ent or "").strip()
            if not ent_clean:
                continue
            if exclude_generic and ent_clean in GENERIC_ENTITIES:
                continue
            by_ent[ent_clean].append(article)

    clusters: list[dict[str, Any]] = []
    for ent, items in by_ent.items():
        if len(items) < min_articles:
            continue
        scores = [(a.get("score") or 0.0) for a in items]
        total = sum(scores)
        if total < min_total_score:
            continue

        top_articles = sorted(
            items, key=lambda a: a.get("score") or 0.0, reverse=True
        )[:3]

        clusters.append(
            {
                "name": ent,
                "articles_count": len(items),
                "total_score": round(total, 1),
                "avg_score": round(total / len(items), 1),
                "top_articles": [
                    {
                        "title": a.get("title", ""),
                        "publisher": a.get("publisher", ""),
                        "score": round(a.get("score") or 0.0, 1),
                        "url": a.get("url", ""),
                    }
                    for a in top_articles
                ],
            }
        )

    # Tri : volume × score, mais favorise le score
    clusters.sort(
        key=lambda c: (c["total_score"], c["articles_count"]), reverse=True
    )
    return clusters[:top_n]


# ---------------------------------------------------------------
# Clustering co-occurrence — regroupement d'entités liées
# ---------------------------------------------------------------


def cluster_entities_by_cooccurrence(
    articles: list[dict],
    *,
    min_articles_per_entity: int = 3,
    jaccard_threshold: float = 0.40,
    min_cluster_size: int = 2,
    max_entities_per_cluster: int = 6,
    top_n: int = 8,
    exclude_generic: bool = True,
) -> list[dict[str, Any]]:
    """Regroupe les entités qui co-occurrent dans les mêmes articles.

    Algorithme single-link sur le Jaccard d'ensembles d'articles :
      1. Pour chaque entité fréquente, on calcule l'ensemble des articles
         où elle apparaît.
      2. Pour chaque paire d'entités, si Jaccard(setA, setB) >= seuil,
         elles sont liées.
      3. Composantes connexes du graphe → clusters.
      4. Pour chaque cluster :
         - articles = union des articles des membres
         - label = entité avec le plus d'articles (la dominante)
         - members = toutes les entités du cluster (capées à max_per_cluster)

    Permet de transformer ["Train", "TGV", "Rhône"] → cluster "Train"
    avec ses 2 membres associés et le total des articles uniques.
    """
    # 1. Set d'articles par entité (par index dans la liste)
    by_ent: dict[str, set[int]] = {}
    by_ent_score: dict[str, float] = {}
    for idx, article in enumerate(articles):
        for ent in article.get("entities_list") or []:
            ent_clean = (ent or "").strip()
            if not ent_clean:
                continue
            if exclude_generic and ent_clean in GENERIC_ENTITIES:
                continue
            by_ent.setdefault(ent_clean, set()).add(idx)
            by_ent_score[ent_clean] = (
                by_ent_score.get(ent_clean, 0.0)
                + (article.get("score") or 0.0)
            )

    # Filtrer les entités peu fréquentes
    eligible = [
        ent for ent, idxs in by_ent.items() if len(idxs) >= min_articles_per_entity
    ]
    if len(eligible) < 2:
        return []

    # 2. Construire les liens (union-find pour composantes connexes)
    parent = {ent: ent for ent in eligible}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, ent_a in enumerate(eligible):
        for ent_b in eligible[i + 1 :]:
            inter = by_ent[ent_a] & by_ent[ent_b]
            if not inter:
                continue
            union_set = by_ent[ent_a] | by_ent[ent_b]
            jacc = len(inter) / len(union_set)
            if jacc >= jaccard_threshold:
                union(ent_a, ent_b)

    # 3. Regrouper par composante connexe
    groups: dict[str, list[str]] = {}
    for ent in eligible:
        root = find(ent)
        groups.setdefault(root, []).append(ent)

    # 4. Construire les clusters finaux
    clusters: list[dict[str, Any]] = []
    for members in groups.values():
        if len(members) < min_cluster_size:
            continue

        # Tri par volume d'articles décroissant → label = dominante
        members_sorted = sorted(
            members, key=lambda e: len(by_ent[e]), reverse=True
        )
        members_capped = members_sorted[:max_entities_per_cluster]

        all_article_idxs: set[int] = set()
        for ent in members:
            all_article_idxs |= by_ent[ent]

        articles_in_cluster = [articles[i] for i in all_article_idxs]
        total_score = sum((a.get("score") or 0.0) for a in articles_in_cluster)
        top_articles = sorted(
            articles_in_cluster,
            key=lambda a: a.get("score") or 0.0,
            reverse=True,
        )[:3]

        clusters.append(
            {
                "label": members_sorted[0],  # entité dominante
                "members": members_capped,
                "members_count": len(members),
                "articles_count": len(all_article_idxs),
                "total_score": round(total_score, 1),
                "avg_score": round(
                    total_score / max(1, len(all_article_idxs)), 1
                ),
                "top_articles": [
                    {
                        "title": a.get("title", ""),
                        "publisher": a.get("publisher", ""),
                        "score": round(a.get("score") or 0.0, 1),
                        "url": a.get("url", ""),
                    }
                    for a in top_articles
                ],
            }
        )

    clusters.sort(
        key=lambda c: (c["total_score"], c["articles_count"]),
        reverse=True,
    )
    return clusters[:top_n]


def entities_in_clusters(clusters: list[dict]) -> set[str]:
    """Set des entités absorbées dans un cluster (pour éviter de les
    afficher en double dans la vue entités plates)."""
    seen: set[str] = set()
    for c in clusters:
        for m in c.get("members") or []:
            seen.add(m)
    return seen
