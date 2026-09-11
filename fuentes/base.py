"""Lo que comparten los dos agentes: el calendario de semanas y la agregación.

Este módulo no sabe de SQLite ni de Postgres. Cada fuente (`leia.py`, `gdp.py`)
se encarga de su base y devuelve la misma lista de **eventos**:

    {"usuario": "czelada", "cuando": datetime(hora Lima, naive), "tipo": "consulta"}

`tipo` es `conversacion` (se abrió un chat) o `consulta` (una pregunta dentro de
un chat). Se cuentan los dos porque miden cosas distintas: las conversaciones
dicen cuántas veces alguien vino a trabajar con el agente, las consultas cuántas
preguntas hizo. El tablero deja elegir cuál se grafica.

El ancla de las semanas es **una sola para todos los agentes** (el lunes del
evento más viejo de cualquiera). Si cada uno numerara desde su propio primer
registro, «Semana 3» sería una fecha distinta según el agente elegido y el
selector mentiría al cambiar de uno a otro.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Perú, UTC-5 y sin horario de verano: un offset fijo alcanza.
LIMA = timezone(timedelta(hours=-5))

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]

METRICAS = ("conversaciones", "consultas")

# El `tipo` de un evento es singular (así se lee al construirlo); la serie que
# alimenta es plural (así se lee en el front). Este mapa es el único lugar donde
# se cruzan los dos vocabularios.
SERIE = {"conversacion": "conversaciones", "consulta": "consultas"}


# ---------------------------------------------------------------- semanas
def lunes_de(d: date) -> date:
    """Lunes de la semana que contiene `d`. weekday(): lun=0 .. dom=6."""
    return d - timedelta(days=d.weekday())


def indice_semana(d: date, ancla: date) -> int:
    """Índice 1-based de la semana de `d` respecto del lunes ancla."""
    return (d - ancla).days // 7 + 1


def etiqueta_semana(n: int, ancla: date) -> str:
    """'Semana N · DD Mmm – DD Mmm' (lunes a domingo de esa semana)."""
    ini = ancla + timedelta(weeks=n - 1)
    fin = ini + timedelta(days=6)
    return (f"Semana {n} · {ini.day:02d} {MESES[ini.month - 1]} "
            f"– {fin.day:02d} {MESES[fin.month - 1]}")


def evento(usuario: str, cuando: datetime, tipo: str) -> dict:
    """Un evento normalizado. `cuando` ya tiene que venir en hora de Lima."""
    if tipo not in SERIE:
        raise ValueError(f"tipo de evento desconocido: {tipo!r}")
    if cuando.tzinfo is not None:
        cuando = cuando.astimezone(LIMA).replace(tzinfo=None)
    return {"usuario": usuario, "cuando": cuando, "tipo": tipo}


def semana_vacia() -> dict:
    return {"dias": DIAS, "conversaciones": {}, "consultas": {}}


# ------------------------------------------------------------- agregación
def agregar(eventos_por_agente: dict[str, list[dict]], ahora: datetime) -> tuple[dict, date]:
    """Eventos crudos -> {agente: {etiqueta de semana: semana}}, más el ancla.

    Todas las semanas de 1 a la semana en curso existen en todos los agentes,
    aunque estén vacías: así el eje del gráfico de barras no tiene huecos y el
    selector de semana sirve igual para los dos.
    """
    todos = [e["cuando"] for evs in eventos_por_agente.values() for e in evs]
    ancla = lunes_de(min(todos).date()) if todos else lunes_de(ahora.date())
    max_semana = max(1, indice_semana(ahora.date(), ancla))
    for c in todos:
        max_semana = max(max_semana, indice_semana(c.date(), ancla))

    datos: dict[str, dict] = {}
    for agente, eventos in eventos_por_agente.items():
        semanas = {n: semana_vacia() for n in range(1, max_semana + 1)}
        for e in eventos:
            n = indice_semana(e["cuando"].date(), ancla)
            if n < 1:
                continue                      # defensivo: nada antes del ancla
            serie = semanas[n][SERIE[e["tipo"]]]
            serie.setdefault(e["usuario"], [0] * 7)[e["cuando"].weekday()] += 1

        for s in semanas.values():
            for m in METRICAS:
                s[m] = dict(sorted(s[m].items()))

        datos[agente] = {etiqueta_semana(n, ancla): semanas[n]
                         for n in sorted(semanas)}
    return datos, ancla


def usuarios_de(semanas: dict) -> list[str]:
    """Todos los usuarios del agente, en orden de primera aparición.

    El color de cada persona sale de esta posición, no del ranking de la semana:
    así conserva el mismo color al moverse entre semanas.
    """
    vistos: list[str] = []
    for s in semanas.values():
        for m in METRICAS:
            for u in s[m]:
                if u not in vistos:
                    vistos.append(u)
    return vistos
