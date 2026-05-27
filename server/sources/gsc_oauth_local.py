"""Mini-serveur local pour récupérer le callback OAuth Google.

Pattern "Google OAuth for installed apps via local loopback" :
  1. On démarre un HTTP server sur 127.0.0.1:{port}
  2. On ouvre le browser sur l'URL d'autorisation Google
  3. Google redirige vers http://localhost:{port}/callback?code=...&state=...
  4. Le handler capture le code, échange contre tokens, persiste, et
     répond avec une page HTML "Connexion OK".
  5. Le serveur s'arrête.

Stdlib only — pas de Flask, pas de FastAPI.
"""

from __future__ import annotations

import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from server.config import settings
from server.sources import gsc


# Templates HTML minimalistes (styling TBR-compatible)
_OK_HTML = """<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <title>Editorial Signal · Connexion GSC OK</title>
  <style>
    html, body { margin: 0; padding: 0; background: #000; color: #fff;
      font-family: -apple-system, "Segoe UI", sans-serif; min-height: 100vh;
      display: flex; align-items: center; justify-content: center; }
    .card { padding: 40px; border: 1px solid #444; border-left: 3px solid #00FF00;
      max-width: 480px; text-align: center; background: #0a0a0a; }
    h1 { margin: 0 0 12px; font-size: 1.5rem; text-transform: uppercase;
      letter-spacing: 1px; color: #00FF00; }
    p { color: #999; line-height: 1.5; }
    code { background: #111; padding: 2px 6px; color: #F50000; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Connexion réussie</h1>
    <p>Le projet <code>{project}</code> est désormais connecté à Google Search Console.</p>
    <p>Tu peux fermer cet onglet et retourner au terminal.</p>
  </div>
</body>
</html>
"""

_ERR_HTML = """<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <title>Editorial Signal · Erreur OAuth</title>
  <style>
    html, body { margin: 0; padding: 0; background: #000; color: #fff;
      font-family: -apple-system, "Segoe UI", sans-serif; min-height: 100vh;
      display: flex; align-items: center; justify-content: center; }
    .card { padding: 40px; border: 1px solid #F50000; border-left: 3px solid #F50000;
      max-width: 540px; background: #0a0a0a; }
    h1 { margin: 0 0 12px; font-size: 1.5rem; text-transform: uppercase;
      letter-spacing: 1px; color: #F50000; }
    pre { color: #999; white-space: pre-wrap; word-break: break-word; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Échec de l'authentification</h1>
    <pre>{error}</pre>
  </div>
</body>
</html>
"""


class _CallbackResult:
    """Conteneur mutable partagé entre threads."""

    def __init__(self) -> None:
        self.received = False
        self.code: str | None = None
        self.state: str | None = None
        self.error: str | None = None


def _build_handler(result: _CallbackResult, expected_state: str):
    """Factory : crée la classe handler avec accès au résultat partagé."""

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Silence les logs HTTP par défaut (sinon stdout pollué)
            return

        def do_GET(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query or "")

            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            err = qs.get("error", [""])[0]
            code = qs.get("code", [""])[0]
            state = qs.get("state", [""])[0]

            if err:
                result.received = True
                result.error = err
                self._respond_html(400, _ERR_HTML.format(error=err))
                return

            if state != expected_state:
                result.received = True
                result.error = (
                    "State CSRF mismatch — possible attaque ou session expirée."
                )
                self._respond_html(400, _ERR_HTML.format(error=result.error))
                return

            if not code:
                result.received = True
                result.error = "Pas de code dans la réponse Google."
                self._respond_html(400, _ERR_HTML.format(error=result.error))
                return

            result.received = True
            result.code = code
            result.state = state
            # Le slug sera décodé depuis le state côté caller
            _, slug = gsc.parse_state(state)
            self._respond_html(200, _OK_HTML.format(project=slug or "?"))

        def _respond_html(self, status: int, body: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            payload = body.encode("utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return _Handler


def run_oauth_flow(
    project_slug: str,
    *,
    timeout_s: int = 180,
    open_browser: bool = True,
) -> dict[str, Any]:
    """Lance le flow OAuth complet et persiste les tokens du projet.

    Args:
        project_slug : projet cible
        timeout_s    : timeout du callback
        open_browser : si False, on imprime juste l'URL (utile pour debug)

    Returns:
        Le payload tokens persisté (cf gsc.exchange_code).
    """
    url, state = gsc.get_authorization_url(project_slug)
    port = settings.gsc_callback_port

    result = _CallbackResult()
    handler_cls = _build_handler(result, expected_state=state)
    server = HTTPServer(("127.0.0.1", port), handler_cls)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"  Mini-serveur OAuth actif sur http://127.0.0.1:{port}/callback")
    if open_browser:
        print("  Ouverture du navigateur vers Google…")
        webbrowser.open(url, new=2)
    else:
        print(f"  Ouvre manuellement : {url}")

    started = time.time()
    try:
        while not result.received:
            if time.time() - started > timeout_s:
                raise RuntimeError(
                    f"Timeout OAuth ({timeout_s}s) — aucune réponse de Google."
                )
            time.sleep(0.2)
    finally:
        server.shutdown()
        server.server_close()

    if result.error:
        raise RuntimeError(f"OAuth échoué : {result.error}")
    if not result.code:
        raise RuntimeError("OAuth échoué : pas de code reçu.")

    tokens = gsc.exchange_code(project_slug, result.code)
    return tokens
