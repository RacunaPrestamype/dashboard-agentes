#!/usr/bin/env python3
# ============================================================================
# build_data.py — genera data.js leyendo la base de cada agente
#
# Un solo tablero para los tres agentes: LeIA (SQLite), Indicadores GDP
# (Postgres) y Agente CS (memoria de Bedrock AgentCore). Cada fuente vive en
# `fuentes/` y devuelve la misma lista de consultas; acá se agregan por semana,
# por usuario y por día, y se escribe el archivo que consume index.html.
#
# Una fuente caída NO tumba el tablero: el agente queda marcado `ok: false` con
# el motivo, los demás se muestran igual y el front avisa en pantalla. Un tablero
# que no abre porque una base de tres no responde no sirve de nada.
#
# Semanas: la Semana 1 arranca el LUNES del evento más viejo de CUALQUIER agente,
# y van de lunes a domingo hasta la semana en curso. El ancla es compartida para
# que «Semana 5» sea la misma semana en los dos agentes.
#
# USO:
#   python3 build_data.py               # contra las bases
#   python3 build_data.py --demo        # sin bases, datos fabricados
#   python3 build_data.py --solo leia   # una sola fuente
# ============================================================================

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fuentes import AGENTES, base

OUT_PATH = Path(__file__).resolve().parent / "data.js"

# Colores por usuario, asignados por orden de aparición en toda la historia del
# agente (no por el ranking de la semana): así una persona conserva su color al
# cambiar de semana. Con más usuarios que colores hay repetición; la leyenda
# sigue siendo lo que identifica.
PALETA = ["#00594C", "#00CC75", "#2a78d6", "#E76F51", "#1E2761",
          "#F4A261", "#4a3aa7", "#8FC9B0", "#2C3E50", "#008300"]


def _total(semanas: dict) -> int:
    return sum(sum(sum(v) for v in s["usuarios"].values()) for s in semanas.values())


def recolectar(claves: list[str]) -> tuple[dict, dict]:
    """Lee cada fuente. Devuelve los eventos por agente y el estado de cada una."""
    eventos, estado = {}, {}
    for clave in claves:
        modulo = AGENTES[clave]
        try:
            eventos[clave] = modulo.leer()
            estado[clave] = {"ok": True, "detalle": ""}
        except Exception as exc:                             # noqa: BLE001
            eventos[clave] = []
            estado[clave] = {"ok": False,
                             "detalle": f"{type(exc).__name__}: {exc}"}
            print(f"   aviso: {clave} sin datos -> {estado[clave]['detalle']}",
                  file=sys.stderr)
    return eventos, estado


def construir(eventos: dict, estado: dict, ahora: datetime) -> tuple[dict, dict]:
    """Los eventos de todas las fuentes -> (datos, meta) tal como los lee el front."""
    por_semana, ancla = base.agregar(eventos, ahora)

    datos, agentes = {}, {}
    for clave, semanas in por_semana.items():
        modulo = AGENTES[clave]
        usuarios = base.usuarios_de(semanas)
        datos[clave] = {
            "nombre": modulo.NOMBRE,
            "descripcion": modulo.DESCRIPCION,
            "semanas": semanas,
        }
        agentes[clave] = {
            "nombre": modulo.NOMBRE,
            "descripcion": modulo.DESCRIPCION,
            "ok": estado[clave]["ok"],
            "detalle": estado[clave]["detalle"],
            "usuarios": len(usuarios),
            "consultas": _total(semanas),
            "colores": {u: PALETA[i % len(PALETA)] for i, u in enumerate(usuarios)},
        }

    meta = {
        "generado": ahora.strftime("%d/%m/%Y %H:%M"),
        "ancla": ancla.strftime("%d/%m/%Y"),
        "agentes": agentes,
        "demo": False,
    }
    return datos, meta


def escribir(datos: dict, meta: dict) -> None:
    js = ("/* Generado por build_data.py — NO editar a mano. "
          f"Actualizado: {meta['generado']} (hora Lima) */\n"
          "window.DASHBOARD_DATA = "
          + json.dumps(datos, ensure_ascii=False, indent=2) + ";\n"
          "window.DASHBOARD_META = "
          + json.dumps(meta, ensure_ascii=False, indent=2) + ";\n")
    OUT_PATH.write_text(js, encoding="utf-8")


def demo() -> tuple[dict, dict]:
    """Datos fabricados, sin tocar ninguna base. Para trabajar el front o ver
    cómo se comporta el tablero antes de conectarlo. Queda marcado en el meta y
    el front lo avisa en pantalla."""
    import random
    rnd = random.Random(7)
    ahora = datetime.now().replace(microsecond=0)
    ancla = base.lunes_de(ahora.date()) - timedelta(weeks=5)
    gente = {
        "leia": ["Ana Lucía Acuña", "czelada", "mfelix", "Bruno Dongo",
                 "Silvia Arrascue", "jllacza", "Pamela Rojas"],
        "gdp": ["Ana Lucía Acuña", "Bruno Dongo", "jllacza", "Pamela Rojas"],
        "analyst": ["nterrazas", "jacuna", "gcastro", "vvicuna", "rochoa"],
    }
    eventos = {}
    for clave, personas in gente.items():
        evs = []
        for semana in range(6):
            lunes = ancla + timedelta(weeks=semana)
            for _ in range(rnd.randint(20, 70)):
                cuando = (datetime.combine(lunes + timedelta(days=rnd.randint(0, 4)),
                                           datetime.min.time())
                          + timedelta(hours=rnd.randint(9, 18), minutes=rnd.randint(0, 59)))
                evs.append(base.evento(rnd.choice(personas), cuando))
        eventos[clave] = evs

    estado = {c: {"ok": True, "detalle": "datos fabricados"} for c in gente}
    datos, meta = construir(eventos, estado, ahora)
    meta["demo"] = True
    return datos, meta


def main() -> None:
    if "--demo" in sys.argv:
        datos, meta = demo()
        escribir(datos, meta)
        print(f"OK (DEMO, datos fabricados) -> {OUT_PATH}")
        return

    claves = list(AGENTES)
    if "--solo" in sys.argv:
        pedido = sys.argv[sys.argv.index("--solo") + 1]
        claves = [c.strip() for c in pedido.split(",") if c.strip() in AGENTES]
        if not claves:
            print(f"--solo: agentes válidos: {', '.join(AGENTES)}", file=sys.stderr)
            raise SystemExit(2)

    eventos, estado = recolectar(claves)
    datos, meta = construir(eventos, estado, datetime.now())
    escribir(datos, meta)

    print(f"OK -> {OUT_PATH}")
    print(f"   semanas: {len(next(iter(datos.values()))['semanas']) if datos else 0}"
          f" | ancla: {meta['ancla']}")
    for clave, a in meta["agentes"].items():
        marca = "ok       " if a["ok"] else "SIN DATOS"
        print(f"   {clave:8} {marca} consultas: {a['consultas']:5} | "
              f"usuarios: {a['usuarios']:3}"
              + (f" | {a['detalle']}" if not a["ok"] else ""))


if __name__ == "__main__":
    main()
