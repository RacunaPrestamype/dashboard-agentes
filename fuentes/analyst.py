"""Fuente Agente CS — memoria de Bedrock AgentCore (AWS).

Una consulta = un item de rol USER dentro de un evento de la memoria. Cada
evento es un turno (pregunta + respuesta), así que contar los USER cuenta
preguntas, igual que `turns` en LeIA y `turnos` en GDP.

No hay base que consultar: se llega por API, y son tres llamadas encadenadas —
`list_actors` -> `list_sessions` -> `list_events`. Las de sesiones y las de
eventos son independientes entre sí, así que van en paralelo; en secuencia esto
tarda ~10 s y en paralelo ~1-2 s.

**Los nombres.** El `actorId` es el `sub` de Cognito: un UUID. Un pie con seis
UUIDs no dice nada, así que se resuelven contra el user pool, que tiene el
correo de cada uno. Si el pool no se puede leer (permisos, otra cuenta), el
tablero no se cae: muestra el UUID corto y sigue. `actors_map.json`, si existe,
pisa cualquier nombre: es la salida manual para los actores que no están en el
pool (hoy, uno de nueve).

La memoria es de solo lectura desde acá: todas las llamadas son `list_*`.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import base

NOMBRE = "Agente CS"
DESCRIPCION = "Consultas del equipo de CS · memoria de AgentCore"

MEMORIA_POR_DEFECTO = "prod_analyst_agent_memory-gHFPoM4f9d"
POOL_POR_DEFECTO = "prod-analyst-agent-users"
REGION_POR_DEFECTO = "us-east-1"

# Vacío a propósito. En LeIA y GDP la lista de cuentas internas ya estaba
# decidida en esos repos; acá no la decidió nadie, y `dacuna` sola es un cuarto
# del tráfico del agente: esconderla por defecto sería falsear el uso. Cuando se
# sepa cuáles son de prueba, se ponen en ANALYST_EXCLUIR_USUARIOS.
EXCLUIDOS_POR_DEFECTO = ""

# Un mapeo a mano actorId -> nombre, para lo que Cognito no resuelve. Opcional.
MAPA_PATH = Path(__file__).resolve().parent.parent / "actors_map.json"

HILOS = int(os.environ.get("ANALYST_HILOS", "16"))


def memoria() -> str:
    return os.environ.get("ANALYST_MEMORY_ID", MEMORIA_POR_DEFECTO)


def region() -> str:
    return os.environ.get("ANALYST_AWS_REGION",
                          os.environ.get("AWS_REGION", REGION_POR_DEFECTO))


def _excluidos() -> set[str]:
    crudo = os.environ.get("ANALYST_EXCLUIR_USUARIOS", EXCLUIDOS_POR_DEFECTO)
    return {e.strip().lower() for e in crudo.split(",") if e.strip()}


def _cliente(servicio: str):
    import boto3
    from botocore.config import Config
    return boto3.client(servicio, region_name=region(), config=Config(
        max_pool_connections=HILOS, retries={"max_attempts": 5, "mode": "adaptive"}))


def _paginar(metodo, clave, **kw):
    token = None
    while True:
        params = dict(kw)
        if token:
            params["nextToken"] = token
        resp = metodo(**params)
        yield from resp.get(clave, [])
        token = resp.get("nextToken")
        if not token:
            return


# ------------------------------------------------------------------ nombres
def _de_cognito() -> dict[str, str]:
    """`sub` -> parte local del correo, leyendo el user pool.

    Best-effort: si falla —no hay permisos, el pool cambió de nombre— devuelve
    vacío y los actores salen con su UUID corto. Que los nombres no se puedan
    resolver no es motivo para no mostrar el uso.
    """
    try:
        cog = _cliente("cognito-idp")
        pool_id = os.environ.get("ANALYST_COGNITO_POOL", "")
        if not pool_id:
            buscado = os.environ.get("ANALYST_COGNITO_POOL_NOMBRE", POOL_POR_DEFECTO)
            for p in cog.list_user_pools(MaxResults=60).get("UserPools", []):
                if p["Name"] == buscado:
                    pool_id = p["Id"]
                    break
        if not pool_id:
            return {}

        nombres, token = {}, None
        while True:
            kw = {"UserPoolId": pool_id, "Limit": 60}
            if token:
                kw["PaginationToken"] = token
            r = cog.list_users(**kw)
            for u in r.get("Users", []):
                at = {a["Name"]: a["Value"] for a in u.get("Attributes", [])}
                sub, correo = at.get("sub"), at.get("email", "")
                if sub and correo:
                    nombres[sub] = correo.split("@")[0]
            token = r.get("PaginationToken")
            if not token:
                return nombres
    except Exception:                                        # noqa: BLE001
        return {}


def _del_archivo() -> dict[str, str]:
    if not MAPA_PATH.exists():
        return {}
    try:
        return {k: v for k, v in json.loads(
            MAPA_PATH.read_text(encoding="utf-8")).items() if v}
    except Exception:                                        # noqa: BLE001
        return {}


def nombres() -> dict[str, str]:
    """Cognito primero, y el archivo pisa: es la corrección manual."""
    mapa = _de_cognito()
    mapa.update(_del_archivo())
    return mapa


# -------------------------------------------------------------- la memoria
def leer() -> list[dict]:
    """Los eventos del Agente CS. Levanta si AWS no responde."""
    mem = memoria()
    cli = _cliente("bedrock-agentcore")

    def sesiones_de(actor_id):
        return list(_paginar(cli.list_sessions, "sessionSummaries",
                             memoryId=mem, actorId=actor_id, maxResults=100))

    def eventos_de(sesion):
        return list(_paginar(cli.list_events, "events", memoryId=mem,
                             actorId=sesion["actorId"], sessionId=sesion["sessionId"],
                             includePayloads=True, maxResults=100))

    actores = [a["actorId"] for a in _paginar(cli.list_actors, "actorSummaries",
                                              memoryId=mem, maxResults=100)]
    with ThreadPoolExecutor(max_workers=HILOS) as pool:
        sesiones = [s for lote in pool.map(sesiones_de, actores) for s in lote]
        eventos = [e for lote in pool.map(eventos_de, sesiones) for e in lote]

    mapa = nombres()
    excluidos = _excluidos()
    salida = []
    for ev in eventos:
        nombre = mapa.get(ev["actorId"]) or ev["actorId"][:8]
        if nombre.lower() in excluidos:
            continue
        cuando = ev["eventTimestamp"]
        if isinstance(cuando, str):
            cuando = datetime.fromisoformat(cuando)
        for p in ev.get("payload", []):
            conv = p.get("conversational")
            if conv and conv.get("role") == "USER":
                salida.append(base.evento(nombre, cuando))
    return salida


def disponible() -> tuple[bool, str]:
    """¿Responde la memoria? Para /salud, sin traerse los eventos."""
    try:
        _cliente("bedrock-agentcore").list_actors(memoryId=memoria(), maxResults=1)
        return True, "ok"
    except Exception as exc:                                 # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"
