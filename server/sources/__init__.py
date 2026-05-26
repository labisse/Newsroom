"""Sources de données externes — MSN, Wikimedia, Google Trends, X Trends.

Chaque module expose `fetch()` qui retourne un dict normalisé prêt à
sérialiser en JSON, et `write_snapshot(payload)` qui l'écrit dans
data/{source}/{timestamp}.json. Les chemins sont gérés par utils.
"""
