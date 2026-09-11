# Tablero de uso de los agentes

Un solo tablero para los dos agentes que están en marcha blanca:

| clave  | agente            | qué hace                                  | base                     |
|--------|-------------------|-------------------------------------------|--------------------------|
| `leia` | **LeIA**          | consultas a la plataforma Gestora          | SQLite (`gestora.db`)    |
| `gdp`  | **Indicadores GDP** | diseño de indicadores · Gerencia de Datos | Postgres (rol `tablero`) |

Es el tablero de LeIA —mismo formato, mismos tres gráficos— con un selector de
agente arriba. Cada agente guarda su uso en una base distinta y con otros
nombres de tabla; acá se normalizan a lo mismo y se grafican igual, así comparar
uno con otro es cambiar un `<select>` y no leer dos pantallas distintas.

No levanta ningún agente ni escribe en ninguna base: solo lee.

---

## 1. Qué muestra

Arriba, cuatro KPIs de la semana elegida: **total**, **usuarios activos**,
**promedio por día** y **día pico**.

Abajo, los tres gráficos del tablero de LeIA:

- **Pie — % de uso por usuario.** Top 5 de la semana; el resto se junta en
  «Otros». Responde *quién* está usando el agente.
- **Barras — por semana.** Todas las semanas desde la primera, con la elegida
  resaltada. Clic en una barra la selecciona. Responde *cómo viene la adopción*.
- **Líneas — por usuario y día de la semana.** Una línea por persona, de lunes a
  domingo. Responde *cómo se reparte la semana* y quién sostiene el uso.

### Las dos métricas

El selector **Métrica** cambia qué cuentan los tres gráficos:

- **Conversaciones** — cuántas veces alguien abrió un chat y se puso a trabajar
  con el agente.
- **Consultas** — cuántas preguntas hizo dentro de esos chats.

Miden cosas distintas y conviene mirar las dos: cinco conversaciones de una
pregunta cada una y una conversación de cinco preguntas dan el mismo número de
consultas y no son el mismo uso.

### Las semanas

La **Semana 1** arranca el lunes del registro más viejo **de cualquiera de los
dos agentes**, y de ahí van de lunes a domingo hasta la semana en curso. El
ancla es compartida a propósito: si cada agente numerara desde su propio primer
registro, «Semana 5» sería una fecha distinta según cuál esté elegido y el
selector mentiría al cambiar de uno a otro. El costo es que el agente que
arrancó después abre con semanas vacías al principio; el tablero abre parado en
la última semana **con movimiento**, no en la última del calendario.

---

## 2. Correrlo

### Local

```bash
cp .env.example .env          # y completar lo que haga falta
pip install -r requirements.txt   # solo si vas a leer la base de GDP
make datos                    # genera data.js leyendo las bases
make servir                   # http://localhost:8095
```

Sin ninguna base a mano:

```bash
make demo                     # data.js con datos fabricados; el tablero lo avisa
```

### Docker

```bash
docker compose up -d --build  # o: make tablero
```

El contenedor regenera `data.js` al arrancar y en cada `/regenerar`, así lo que
se sirve nace fresco de las bases.

### Que una base no responda no es un problema del tablero

Si una fuente falla, ese agente queda marcado *sin datos* con el motivo en
pantalla y **el otro se muestra igual**. Un tablero que no abre porque una base
de dos no contesta no le sirve a nadie. `GET /salud` dice cuál está viva.

---

## 3. Configuración

Todo por variables de entorno; ninguna es obligatoria.

| variable                | por defecto                                      | qué hace |
|-------------------------|--------------------------------------------------|----------|
| `LEIA_DB_PATH`          | `../LeIA/db/gestora.db`                          | el archivo SQLite de LeIA |
| `LEIA_EXCLUIR_USUARIOS` | `dacuna,admin,cpardave,dbaldeon`                 | cuentas internas; se comparan contra la parte local del correo |
| `GDP_BD_URL`            | *(vacío)*                                        | Postgres del agente GDP, con el rol `tablero` |
| `GDP_EXCLUIR_EMAILS`    | `evaluacion@prestamype.com,qa@prestamype.com`    | cuentas de QA y de la batería de evaluación |
| `HOST` / `PORT`         | `0.0.0.0` / `8080`                               | dónde escucha `serve.py` |
| `PUERTO_TABLERO`        | `8095`                                           | puerto publicado por compose |

En compose, `LEIA_DB_DIR` es la carpeta del host con `gestora.db`.

### El tablero nunca escribe

Cada fuente se conecta con lo mínimo para leer:

- **LeIA** abre el archivo con `mode=ro`. A propósito **sin** `immutable=1`: la
  base está en WAL, e ignorar el `-wal` deja fuera todo lo escrito desde el
  último checkpoint, o sea las consultas de hoy. Por eso el volumen se monta
  `rw` aunque no se escriba — SQLite necesita tocar el `-shm` para leer el
  `-wal`; la conexión sigue siendo de solo lectura.
- **GDP** usa el rol `tablero`, que solo tiene `SELECT` (`db/04_rol_tablero.sh`
  en ese repo). Nunca el rol `agente`: ese escribe, y un proceso de reporting no
  tiene por qué poder.

Lo único que este proceso escribe es su propio `data.js`.

---

## 4. De dónde sale cada número

| métrica        | LeIA                              | GDP |
|----------------|-----------------------------------|-----|
| conversaciones | una fila de `chats`               | una fila de `conversaciones` |
| consultas      | una fila de `turns`               | una fila de `turnos` con `estado <> 'en_curso'` |
| usuario        | `chats.user_id` → `users`         | `conversaciones.usuario_id` → `usuarios` |
| nombre         | `display_name`, si no el correo sin dominio | `usuarios.nombre`, si no el correo sin dominio |
| hora           | `created_at` es UTC → se pasa a Lima | `timestamptz` → `AT TIME ZONE 'America/Lima'` |

Tres decisiones que vale explicitar:

- **Ningún turno se filtra por estado en LeIA**, y en GDP solo se dejan fuera los
  `en_curso`. Un turno que terminó en error igual fue una pregunta que alguien
  hizo. Los `en_curso` de GDP son corridas abiertas —o colgadas porque el
  proceso murió—, no preguntas atendidas.
- **Las conversaciones ocultas de GDP cuentan.** `oculta_en` es el «borrar» del
  panel lateral, un gesto de la UI: la conversación existió.
- **La hora es siempre la de Lima.** Sin convertir, todo lo de después de las
  19:00 cae en el día siguiente y los días pico salen corridos.

---

## 5. Los archivos

```
index.html        el tablero (Chart.js por CDN). Lee window.DASHBOARD_DATA.
data.js           lo genera build_data.py. El versionado está vacío a propósito.
build_data.py     orquesta: lee cada fuente, agrega y escribe data.js.
serve.py          sirve la carpeta + /regenerar y /salud.
fuentes/
  base.py         semanas, agregación y el formato del evento. No sabe de bases.
  leia.py         SQLite de LeIA  -> eventos
  gdp.py          Postgres de GDP -> eventos
```

El corte es ese: **una fuente sabe de su base y de nada más**, y devuelve
siempre lo mismo:

```python
{"usuario": "czelada", "cuando": datetime(hora Lima), "tipo": "consulta"}
```

`base.py` agrega esos eventos por semana, usuario y día. El front no sabe de
dónde salieron.

### Agregar un agente

1. Un módulo en `fuentes/` con `NOMBRE`, `DESCRIPCION`, `leer()` y
   `disponible()`.
2. Su línea en `AGENTES`, en `fuentes/__init__.py`.

Nada más: selector, semanas, colores, KPIs y los tres gráficos salen solos.

---

## 6. Endpoints

| ruta         | qué hace |
|--------------|----------|
| `/`          | el tablero |
| `/regenerar` | relee las bases y reescribe `data.js`. Es el botón «Actualizar» |
| `/salud`     | si responde la base de cada agente, y si hay `data.js` |

```bash
make salud     # curl /salud formateado
```

---

Analítica Avanzada & AI · Prestamype Holding
