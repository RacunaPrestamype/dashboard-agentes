"""Fuente LeIA — SQLite (`db/gestora.db`, esquema v3).

Dos tablas dan los dos tipos de evento:
  conversaciones -> `chats`  (una fila por chat abierto en la barra lateral)
  consultas      -> `turns`  (una fila por pregunta; con ramas, una por rama)

El autor se llega por `chats.user_id`: `turns` no tiene usuario propio.

`created_at` es TEXT ISO-8601 en **UTC** (termina en Z). Se pasa a hora de Lima
antes de decidir a qué día y semana pertenece: sin eso, todo lo de después de
las 19:00 de Lima cae en el día siguiente.

Se abre en solo-lectura (`mode=ro`): el tablero nunca escribe. A propósito NO se
usa `immutable=1` — con la base en WAL, ignorar el -wal deja fuera lo escrito
desde el último checkpoint, o sea las consultas de hoy.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from . import base

NOMBRE = "LeIA"
DESCRIPCION = "Consultas a la plataforma Gestora"

# En el contenedor la base viene del volumen compartido; en local, del repo
# vecino. Cualquiera de las dos se puede pisar con la variable de entorno.
RUTA_POR_DEFECTO = (Path(__file__).resolve().parents[2] / "LeIA" / "db" / "gestora.db")

# Cuentas internas (admin, desarrollo, pruebas). Se comparan contra la parte
# local del correo, en minúsculas.
EXCLUIDOS_POR_DEFECTO = "dacuna,admin,cpardave,dbaldeon"

CONVERSACIONES = """
SELECT u.username, u.display_name, c.created_at
FROM chats c
JOIN users u ON u.id = c.user_id
"""

# Sin filtro por `status`: un turno que terminó en error o timeout igual fue una
# consulta que la persona hizo, y es lo que cuenta el tablero de LeIA.
CONSULTAS = """
SELECT u.username, u.display_name, t.created_at
FROM turns t
JOIN chats c ON c.id = t.chat_id
JOIN users u ON u.id = c.user_id
"""


def ruta() -> Path:
    return Path(os.environ.get("LEIA_DB_PATH", RUTA_POR_DEFECTO))


def _excluidos() -> set[str]:
    crudo = os.environ.get("LEIA_EXCLUIR_USUARIOS", EXCLUIDOS_POR_DEFECTO)
    return {e.strip().lower() for e in crudo.split(",") if e.strip()}


def _nombre(username: str | None, display: str | None) -> str:
    """El nombre para mostrar; nunca el id. Sin display_name, el correo sin dominio."""
    if display and display.strip():
        return display.strip()
    return (username or "").split("@")[0]


def _a_lima(iso: str) -> datetime:
    return (datetime.fromisoformat(iso.replace("Z", "+00:00"))
            .astimezone(base.LIMA).replace(tzinfo=None))


def leer() -> list[dict]:
    """Los eventos de LeIA. Levanta si la base no está: el que llama decide."""
    db = ruta()
    if not db.exists():
        raise FileNotFoundError(f"no está la base de LeIA: {db}")

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        filas = {
            "conversacion": conn.execute(CONVERSACIONES).fetchall(),
            "consulta": conn.execute(CONSULTAS).fetchall(),
        }
    finally:
        conn.close()

    excluidos = _excluidos()
    eventos = []
    for tipo, rs in filas.items():
        for username, display, creado in rs:
            if (username or "").split("@")[0].lower() in excluidos:
                continue
            eventos.append(base.evento(_nombre(username, display),
                                       _a_lima(creado), tipo))
    return eventos


def disponible() -> tuple[bool, str]:
    """¿Se puede leer la base? Para /salud, sin traerse las filas."""
    db = ruta()
    if not db.exists():
        return False, f"no existe {db}"
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            conn.execute("SELECT 1 FROM turns LIMIT 1").fetchone()
        finally:
            conn.close()
        return True, "ok"
    except Exception as exc:                                 # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
