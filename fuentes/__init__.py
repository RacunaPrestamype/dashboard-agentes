"""Las fuentes del tablero: un módulo por agente, todos con la misma salida.

Un agente nuevo es un módulo con `NOMBRE`, `DESCRIPCION` y `leer() -> [evento]`
(ver `base.evento`), más su línea en `AGENTES`. El resto —semanas, agregación,
front— no se toca.
"""

from . import analyst, gdp, leia

# clave (la que viaja en data.js y en la URL) -> módulo. El orden es el de los
# selectores del tablero.
AGENTES = {
    "leia": leia,
    "gdp": gdp,
    "analyst": analyst,
}
