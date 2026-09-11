#!/usr/bin/env python3
# ============================================================================
# serve.py — sirve el tablero estático y expone /regenerar y /salud
#
# Sirve los archivos de esta carpeta (index.html, data.js) y añade:
#
#   GET /regenerar   corre build_data.py: lee las bases y reescribe data.js.
#                    Es lo que hace el botón «Actualizar» del tablero.
#   GET /salud       si responde la base de cada agente, y si hay data.js.
#
# El tablero NUNCA escribe en las bases: LeIA se abre con `mode=ro` y GDP se
# conecta con el rol `tablero`, que solo tiene SELECT. Lo único que escribe este
# proceso es su propio data.js.
#
# En contenedor escucha en 0.0.0.0 (alcanzable por la red interna de Docker); la
# exposición pública la da el reverse proxy.
#
# USO:
#   python3 serve.py [puerto]      (por defecto 8080)
#   PORT=8080 HOST=0.0.0.0 python3 serve.py
# ============================================================================

import json
import os
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fuentes import AGENTES

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build_data.py"
DATA = ROOT / "data.js"

# Regenerar recorre las dos bases enteras. Hoy es barato; el timeout está para
# que un botón no pueda colgar el proceso.
TIMEOUT_S = 120


def _generar() -> subprocess.CompletedProcess:
    """Corre build_data.py, que lee las bases y reescribe data.js."""
    return subprocess.run(
        [sys.executable, str(BUILD)],
        capture_output=True, text=True, timeout=TIMEOUT_S, cwd=str(ROOT),
    )


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # index.html y data.js cambian con cada /regenerar. Sin Cache-Control el
        # navegador aplica frescura heurística y reusa la copia vieja al
        # refrescar (el <script src="data.js"> inicial no lleva cache-buster).
        # Forzar revalidación: como el Last-Modified cambia, el server devuelve
        # 200 con lo nuevo y el refresh siempre muestra el último dato.
        if self.path.split("?")[0].rstrip("/") in ("", "/index.html", "/data.js"):
            self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def do_GET(self):
        ruta = self.path.split("?")[0].rstrip("/")
        if ruta == "/regenerar":
            return self._regenerar()
        if ruta == "/salud":
            return self._salud()
        return super().do_GET()

    def log_message(self, formato, *args):
        # el log por defecto imprime cada GET de fuente y favicon; solo interesan
        # los dos endpoints propios
        if self.path.split("?")[0].rstrip("/") in ("/regenerar", "/salud"):
            super().log_message(formato, *args)

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _regenerar(self):
        try:
            r = _generar()
            ok = r.returncode == 0
            self._json(200 if ok else 500,
                       {"ok": ok, "out": (r.stdout or "") + (r.stderr or "")})
        except Exception as e:                  # noqa: BLE001
            self._json(500, {"ok": False, "error": str(e)})

    def _salud(self):
        """Lo que degrada el tablero sin tumbarlo: cada base, y si hay data.js.

        `ok` es cierto con AL MENOS una fuente viva: con una caída el tablero
        sigue sirviendo la otra, y eso no amerita reiniciar el contenedor.
        """
        fuentes = {}
        for clave, modulo in AGENTES.items():
            viva, detalle = modulo.disponible()
            fuentes[clave] = {"ok": viva, "detalle": detalle}
        self._json(200, {
            "ok": any(f["ok"] for f in fuentes.values()) and DATA.exists(),
            "fuentes": fuentes,
            "data_js": DATA.exists(),
        })


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8080))

    # Regenera al arrancar, así lo que se sirve nace fresco de las bases (el
    # data.js versionado es solo un fallback vacío). Best-effort: si falla, se
    # sirve lo que haya y queda el botón «Actualizar».
    try:
        r = _generar()
        estado = "regenerado" if r.returncode == 0 else "NO regenerado"
        print(f"[arranque] data.js {estado}: {(r.stdout or r.stderr or '').strip()[:300]}")
    except Exception as e:                       # noqa: BLE001
        print(f"[arranque] no se pudo regenerar data.js: {e}")

    httpd = ThreadingHTTPServer((host, port), partial(Handler, directory=str(ROOT)))
    print(f"Tablero en http://{host}:{port}  (endpoints: /regenerar, /salud)")
    httpd.serve_forever()
