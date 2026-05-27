# Setup Google Search Console — Editorial Signal

Connexion OAuth + extraction des URLs ayant généré du trafic Google
Discover sur les 12 derniers mois, par projet (site).

> Multi-projet : chaque projet a ses propres tokens dans
> `data/projects/{slug}/gsc_tokens.json`. Le slug est défini dans
> `data/projects/index.json`.

---

## 1. Configuration côté Google Cloud Console (une seule fois)

Tu peux soit réutiliser le **Client OAuth** déjà créé pour Audit
Discover, soit en créer un nouveau dédié à Editorial Signal. La
deuxième option est plus propre (séparation des apps).

### Création d'un nouveau Client OAuth

1. Va sur https://console.cloud.google.com/apis/credentials
2. Sélectionne (ou crée) un **projet Google Cloud** (ex. "Editorial Signal").
3. **Activer l'API Search Console** :
   - https://console.cloud.google.com/apis/library/searchconsole.googleapis.com
   - Clique **Activer**.
4. **Configurer l'écran OAuth** (si pas déjà fait) :
   - https://console.cloud.google.com/apis/credentials/consent
   - Type **External** (utilisateurs Google standard).
   - Nom de l'app : `Editorial Signal`.
   - Email de support : ton email.
   - Domaines : laisse vide pour le POC.
   - Étape "Scopes" : passer (on demande le scope au runtime).
   - Étape "Test users" : **ajoute ton email Google** (sinon Google bloque
     les apps non publiées).
5. **Créer le Client ID OAuth** :
   - https://console.cloud.google.com/apis/credentials → **Create credentials → OAuth client ID**
   - Type : **Web application**
   - Name : `Editorial Signal local`
   - **Authorized redirect URIs** : `http://localhost:8765/callback`
   - Clique **Create**, copie **Client ID** et **Client Secret**.

### Réutiliser le Client de Audit Discover

Si tu préfères réutiliser celui d'Audit Discover :
- Ajoute `http://localhost:8765/callback` aux **Authorized redirect URIs**
  de ce Client OAuth.
- Copie les Client ID / Secret depuis le `.env` d'Audit Discover
  (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`).

---

## 2. Configurer `.env` Editorial Signal

Édite `.env` à la racine du projet :

```env
GSC_CLIENT_ID=<colle ton Client ID>
GSC_CLIENT_SECRET=<colle ton Client Secret>
GSC_REDIRECT_URI=http://localhost:8765/callback
GSC_CALLBACK_PORT=8765
```

`.env` est gitignored — les secrets ne fuiront jamais sur GitHub.

---

## 3. Première connexion d'un projet

Choisis un projet existant dans `data/projects/index.json` (par défaut
`parismatch` ou `futura-sciences`) ou édite ce fichier pour ajouter un
nouveau slug.

```bash
# Active le venv si besoin
source .venv/bin/activate

# Lance le flow OAuth — un mini-serveur localhost:8765 démarre,
# le navigateur s'ouvre, tu autorises l'accès, le serveur s'arrête.
python -m server.cli gsc-connect --project=parismatch
```

Sortie attendue :
```
Editorial Signal — GSC connect [parismatch]

  Mini-serveur OAuth actif sur http://127.0.0.1:8765/callback
  Ouverture du navigateur vers Google…

✓ Connexion réussie.
  Tokens : data/projects/parismatch/gsc_tokens.json
  Connecté le : 2026-05-27T...
```

---

## 4. Vérifier les propriétés accessibles

```bash
python -m server.cli gsc-sites --project=parismatch
```

Affiche la liste des propriétés Search Console auxquelles ton compte
Google a accès. Note l'URL exacte (`sc-domain:parismatch.com` ou
`https://www.parismatch.com/`) que tu utiliseras pour le fetch.

---

## 5. Extraire les URLs Discover sur 12 mois

```bash
# Site par défaut (la 1re propriété accessible) sur 365 jours
python -m server.cli gsc-fetch --project=parismatch

# Ou avec un site explicite et une fenêtre custom
python -m server.cli gsc-fetch \
    --project=parismatch \
    --site=sc-domain:parismatch.com \
    --days=365
```

Sortie attendue :
```
Editorial Signal — GSC fetch [parismatch] (Discover, 365j)

  XXX URLs récupérées en X.Xs
  Période : 2025-05-27 → 2026-05-27
  Upsert : +XXX nouvelles · ~0 mises à jour · XXX total
  Fichier : data/projects/parismatch/discover_history.jsonl
```

Cette commande est **idempotente** et **incrémentale** :
- Une URL déjà connue → MAX entre l'ancienne et la nouvelle métrique
- Nouvelle URL → insert
- Format JSONL : 1 ligne = 1 URL, dédupliquée par hash SHA-256

---

## 6. (Optionnel) Scraper les titres éditoriaux

GSC retourne uniquement URL + clics + impressions. Pour récupérer le
**titre éditorial** de chaque article (nettoyé du suffixe " - Paris Match"
ou " | Paris Match"), on scrape la balise `<title>`.

```bash
# Scrape tous les titres manquants (politesse ~0.5s/req)
python -m server.cli gsc-scrape-titles --project=parismatch

# Limiter à N pour ne pas tout faire d'un coup
python -m server.cli gsc-scrape-titles --project=parismatch --limit=100
```

Idempotent : les URLs déjà scrapées (succès OU échec) sont sautées.
Si une URL a échoué (page 404, timeout), elle est marquée avec
`title = null` et `title_scraped_at = timestamp` — pour la re-tenter
plus tard il faudra reset le champ manuellement.

---

## 7. État global

```bash
python -m server.cli gsc-status
```

Tableau : projet · connecté oui/non · nb URLs en base · top URL.

---

## 8. Déconnexion

```bash
python -m server.cli gsc-disconnect --project=parismatch
```

Supprime `data/projects/parismatch/gsc_tokens.json`. L'historique
JSONL reste intact.

---

## Stockage

```
data/
└── projects/
    └── {slug}/
        ├── gsc_tokens.json         # secret, gitignored
        └── discover_history.jsonl  # commit OK (pas de PII)
```

Le `.env` global et les tokens par projet sont gitignored (cf .gitignore
ligne `*.json` dans `data/projects/*/gsc_tokens.json` — vérifie).

L'historique JSONL est commit-friendly : pas de tokens, pas de PII,
juste des URLs publiques + métriques.

---

## Quotas GSC

- **API Search Console** : 1200 requêtes/minute par projet GCP, 25k
  lignes/requête, 16 mois d'historique max.
- Notre `fetch_search_analytics` pagine automatiquement par tranches
  de 25k jusqu'à `GSC_MAX_TOTAL_ROWS` (défaut 100k).
- Pour un média avec >100k URLs Discover, ajuste la constante
  `GSC_MAX_TOTAL_ROWS` dans `server/sources/gsc.py`.

---

## Roadmap (sprints suivants)

- **Sprint 2** : GitHub Action quotidienne → `gsc-fetch` auto sur tous
  les projets connectés
- **Sprint 3** : Embeddings (Voyage API ou TF-IDF) sur les titres pour
  recherche sémantique
- **Sprint 4** : Croisement temps-réel × historique → angles éditoriaux
  + variantes de titres performants pour un sujet émergent
