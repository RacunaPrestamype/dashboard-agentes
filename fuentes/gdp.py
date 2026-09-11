"""Fuente GDP — Postgres del agente de diseño de indicadores.

Una consulta = una fila de `turnos` (una corrida del grafo = una pregunta).

Tres cosas que vale saber de este esquema:

- **El autor de un turno no está en `turnos`.** Se llega por
  `conversaciones.usuario_id`, así que hasta las consultas pasan por
  `conversaciones`.

- **Las horas son `timestamptz`.** `AT TIME ZONE 'America/Lima'` las baja a hora
  local acá, en la base, y a Python llegan ya convertidas (naive).

- **Los turnos `en_curso` no cuentan.** Son corridas abiertas —o colgadas por un
  proceso que murió—, no preguntas atendidas. Los otros tres estados (ok, error,
  cancelado) sí: la persona preguntó igual.

Las conversaciones ocultas SÍ entran: `oculta_en` es el «borrar» del panel
lateral, un gesto de la UI, no un borrado — la conversación existió.

Se conecta con el rol `tablero`, que solo tiene SELECT (db/04_rol_tablero.sh del
repo del agente). Acá el equivalente al `mode=ro` de SQLite es el rol, no un flag.
"""

from __future__ import annotations

import os

from . import base

NOMBRE = "Indicadores GDP"
DESCRIPCION = "Diseño de indicadores · Gerencia de Datos"

EXCLUIDOS_POR_DEFECTO = "evaluacion@prestamype.com,qa@prestamype.com"

# `<> ALL(array)` es TRUE con el array vacío: sin exclusiones la consulta no
# cambia de forma.
_SIN_EXCLUIDOS = "lower(u.email) <> ALL(%(excluidos)s)"

# El nombre para mostrar: el del IdP si lo mandó, si no el correo sin dominio.
_NOMBRE = "COALESCE(NULLIF(btrim(u.nombre), ''), split_part(u.email, '@', 1))"

CONSULTAS = f"""
SELECT {_NOMBRE} AS usuario,
       (t.inicio AT TIME ZONE 'America/Lima') AS cuando
FROM turnos t
JOIN conversaciones c ON c.id = t.conversacion_id
JOIN usuarios       u ON u.id = c.usuario_id
WHERE {_SIN_EXCLUIDOS}
  AND t.estado <> 'en_curso'
"""


def url() -> str:
    return os.environ.get("GDP_BD_URL", "")


def _excluidos() -> list[str]:
    crudo = os.environ.get("GDP_EXCLUIR_EMAILS", EXCLUIDOS_POR_DEFECTO)
    return [e.strip().lower() for e in crudo.split(",") if e.strip()]


def leer() -> list[dict]:
    """Los eventos del agente GDP. Levanta si no hay URL o la base no responde."""
    if not url():
        raise RuntimeError("falta GDP_BD_URL")

    import psycopg                     # solo se importa si la fuente se usa

    with psycopg.connect(url(), connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(CONSULTAS, {"excluidos": _excluidos()})
        return [base.evento(usuario, cuando) for usuario, cuando in cur.fetchall()]


def disponible() -> tuple[bool, str]:
    """¿Responde la base? Para /salud, sin traerse las filas."""
    if not url():
        return False, "falta GDP_BD_URL"
    try:
        import psycopg
        with psycopg.connect(url(), connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True, "ok"
    except Exception as exc:                                 # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
