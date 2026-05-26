"""Module de scoring — croise les 4 sources et produit des sujets scorés.

Pipeline :
  1. lit data/{msn,wikimedia,google_trends,x_trends}/latest.json
  2. pour chaque article MSN, cherche les matches dans les 3 autres sources
     via Jaccard sur tokens normalisés
  3. calcule un Signal Score 0–100 selon la pondération du CdC
     (adaptée car GSC + Google News ne sont pas branchés pour le POC)
  4. trie, garde le top et écrit data/sujets/latest.json

Sortie consommée par le front statique (remplacement du mock data.js).
"""
