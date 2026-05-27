"""Normalisation et tokenisation FR pour le matching de signaux.

Stratégie volontairement simple (pas de dépendance NLP lourde) :
  1. lowercase
  2. retrait des diacritiques (étienne → etienne)
  3. tokenisation sur tout ce qui n'est pas alphanumérique
  4. filtrage des stopwords FR + tokens trop courts (< 2 chars)
  5. retrait des chiffres purs (ex. années) sauf si elles sont seules
     dans le titre — ce qui n'arrive jamais en pratique

Suffisant pour du Jaccard sur titres courts (articles, queries, pages
Wikipedia). Si on en a besoin un jour, on raffinera avec un stemmer FR
ou un modèle d'embeddings, mais pour un POC c'est largement assez.
"""

from __future__ import annotations

import re
import unicodedata

# Stopwords FR courts (déterminants, prépositions, conjonctions, pronoms,
# verbes très fréquents). Volontairement restreint : on garde tout ce
# qui pourrait être un mot porteur de sens (noms propres, thématiques).
STOPWORDS_FR: frozenset[str] = frozenset(
    {
        # Articles & déterminants
        "le", "la", "les", "un", "une", "des", "du", "de", "d", "l",
        "ce", "cet", "cette", "ces", "mon", "ma", "mes", "ton", "ta",
        "tes", "son", "sa", "ses", "notre", "votre", "leur", "leurs",
        # Pronoms
        "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
        "me", "te", "se", "lui", "leur", "y", "en", "qui", "que", "quoi",
        "dont", "où", "ou",
        # Prépositions / conjonctions
        "à", "au", "aux", "par", "pour", "avec", "sans", "sur", "sous",
        "dans", "entre", "vers", "chez", "et", "ni", "mais", "or", "car",
        "donc", "si", "comme", "quand", "que",
        # Verbes très fréquents (formes courantes)
        "est", "sont", "était", "ont", "a", "ai", "avez", "avoir", "être",
        "fait", "faire", "va", "vont", "allait", "peut", "peuvent",
        "doit", "doivent",
        # Adverbes courants
        "plus", "moins", "très", "trop", "bien", "tout", "tous", "toute",
        "toutes", "encore", "déjà", "aussi", "ainsi", "alors", "puis",
        "ici", "là", "non", "oui", "pas", "ne", "n",
        # Mots vides éditoriaux fréquents en titres
        "the", "les", "info", "actu", "actus", "actualité", "actualites",
        "vidéo", "video", "photo", "photos", "exclusif", "exclusive",
        # Mots d'accroche très fréquents en titres (sinon faux positifs)
        "voici", "voila", "ceci", "cela",
        "ans",  # "à 17 ans", "à 80 ans" — peu informatif
        "an",
        "direct",  # "EN DIRECT, ..." typique Le Monde
    }
)

# Regex pour découper sur tout ce qui n'est ni lettre ni chiffre
_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def strip_accents(text: str) -> str:
    """étienne → etienne, Noël → Noel."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    """Normalise une chaîne pour matching : lower + sans accents."""
    return strip_accents(text or "").lower()


def tokenize(text: str, *, min_len: int = 2) -> list[str]:
    """Tokenise un texte FR en liste de tokens significatifs.

    Args:
        text: texte à tokeniser
        min_len: longueur minimale d'un token (défaut 2)
    """
    if not text:
        return []

    normalized = normalize_text(text)
    raw_tokens = _TOKEN_RE.split(normalized)

    return [
        t
        for t in raw_tokens
        if len(t) >= min_len and t not in STOPWORDS_FR and not t.isdigit()
    ]


def token_set(text: str) -> set[str]:
    """Set de tokens uniques (pour Jaccard)."""
    return set(tokenize(text))
