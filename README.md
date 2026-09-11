# Tablero de uso de los agentes

Un solo tablero para los tres agentes:

| clave     | agente              | qué hace                                  | de dónde salen los datos |
|-----------|---------------------|-------------------------------------------|--------------------------|
| `leia`    | **LeIA**            | consultas a la plataforma Gestora          | SQLite (`gestora.db`)    |
| `gdp`     | **Indicadores GDP** | diseño de indicadores · Gerencia de Datos  | Postgres (rol `tablero`) |
| `analyst` | **Agente CS**       | consultas del equipo de CS                 | memoria de Bedrock AgentCore |

Es el tablero de LeIA —mismo formato, mismos tres gráficos— con un selector de
agente arriba. Cada agente guarda su uso en otro lado y con otros nombres; acá
se normalizan a lo mismo y se grafican igual, así comparar uno con otro es
cambiar un `<select>` y no leer tres pantallas distintas.

No levanta ningún agente ni escribe en ninguna fuente: solo lee.

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

### La unidad es la consulta

Todo el tablero cuenta **consultas**: preguntas que una persona le hizo al
agente. Es lo único que significa lo mismo en los tres, aunque cada uno la
guarde distinto —una fila de `turns`, una de `turnos`, un mensaje de rol USER en
la memoria de AgentCore—. No hay selector de métrica: un tablero donde el mismo
gráfico puede estar contando dos cosas distintas se lee mal apenas alguien manda
una captura sin decir qué tenía elegido.

### Las semanas

La **Semana 1** arranca el lunes del registro más viejo **de cualquiera de los
tres agentes**, y de ahí van de lunes a domingo hasta la semana en curso. El
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
pip install -r requirements.txt   # psycopg (GDP) y boto3 (Agente CS)
make datos                    # genera data.js leyendo las tres fuentes
make servir                   # http://localhost:8095
```

Sin ninguna fuente a mano:

```bash
make demo                     # data.js con datos fabricados; el tablero lo avisa
```

### Docker

```bash
docker compose up -d --build  # o: make tablero
```

El contenedor regenera `data.js` al arrancar y en cada `/regenerar`, así lo que
se sirve nace fresco de las fuentes.

### Que una fuente no responda no es un problema del tablero

Si una fuente falla —la base caída, la sesión de AWS vencida— ese agente queda
marcado *sin datos* con el motivo en pantalla y **los otros se muestran igual**.
Un tablero que no abre porque una fuente de tres no contesta no le sirve a
nadie. `GET /salud` dice cuál está viva.

---

## 3. Configuración

Todo por variables de entorno; ninguna es obligatoria.

| variable                   | por defecto                                   | qué hace |
|----------------------------|-----------------------------------------------|----------|
| `LEIA_DB_PATH`             | `../LeIA/db/gestora.db`                       | el archivo SQLite de LeIA |
| `LEIA_EXCLUIR_USUARIOS`    | `dacuna,admin,cpardave,dbaldeon`              | cuentas internas; se comparan contra la parte local del correo |
| `GDP_BD_URL`               | *(vacío)*                                     | Postgres del agente GDP, con el rol `tablero` |
| `GDP_EXCLUIR_EMAILS`       | `evaluacion@prestamype.com,qa@prestamype.com` | cuentas de QA y de la batería de evaluación |
| `AWS_PROFILE`              | `prod`                                        | la sesión de AWS para el Agente CS |
| `ANALYST_MEMORY_ID`        | `prod_analyst_agent_memory-gHFPoM4f9d`        | la memoria de AgentCore que se lee |
| `ANALYST_COGNITO_POOL`     | *(se busca por nombre)*                       | el user pool del que salen los nombres |
| `ANALYST_EXCLUIR_USUARIOS` | *(vacío)*                                     | ver abajo |
| `HOST` / `PORT`            | `0.0.0.0` / `8080`                            | dónde escucha `serve.py` |
| `PUERTO_TABLERO`           | `8095`                                        | puerto publicado por compose |
| `UID_HOST` / `GID_HOST`    | `1000`                                        | con qué usuario corre el contenedor, para poder leer `~/.aws` |

**El Agente CS no excluye a nadie por defecto.** En LeIA y GDP la lista de cuentas
internas ya estaba decidida en esos repos; acá no la decidió nadie todavía, y
`dacuna` sola es un cuarto del tráfico del agente: esconderla por defecto sería
falsear el uso. Cuando se sepa cuáles son de prueba, van en
`ANALYST_EXCLUIR_USUARIOS`.

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
- **Agente CS** solo hace llamadas `list_*` a AgentCore y a Cognito. Las
  credenciales son las del host, montadas en `/aws` en solo lectura.

Lo único que este proceso escribe es su propio `data.js`.

---

## 4. De dónde sale cada número

|              | LeIA                                 | GDP | Agente CS |
|--------------|--------------------------------------|-----|---------|
| una consulta | fila de `turns`                      | fila de `turnos` con `estado <> 'en_curso'` | item de rol `USER` en un evento |
| usuario      | `chats.user_id` → `users`            | `conversaciones.usuario_id` → `usuarios` | `actorId` (el `sub` de Cognito) |
| nombre       | `display_name`, si no el correo sin dominio | `usuarios.nombre`, si no el correo sin dominio | el correo del user pool, si no el UUID corto |
| hora         | `created_at` es UTC → se pasa a Lima | `timestamptz` → `AT TIME ZONE 'America/Lima'` | `eventTimestamp` trae tz → se pasa a Lima |

Cuatro decisiones que vale explicitar:

- **Ningún turno se filtra por estado en LeIA**, y en GDP solo se dejan fuera los
  `en_curso`. Un turno que terminó en error igual fue una pregunta que alguien
  hizo. Los `en_curso` de GDP son corridas abiertas —o colgadas porque el
  proceso murió—, no preguntas atendidas.
- **La hora es siempre la de Lima.** Sin convertir, todo lo de después de las
  19:00 cae en el día siguiente y los días pico salen corridos.
- **Los nombres del Agente CS se resuelven contra Cognito**, porque el `actorId` es
  un UUID y un pie con seis UUIDs no dice nada. Si el pool no se puede leer, el
  tablero muestra el UUID corto y sigue: que no se resuelva un nombre no es
  motivo para no mostrar el uso.
- **`actors_map.json` pisa cualquier nombre.** Es la salida manual para los
  actores que no están en el pool (hoy, tres de nueve): un JSON plano de
  `actorId` a nombre, en la raíz del repo.

---

## 5. Los archivos

```
index.html        el tablero (Chart.js por CDN). Lee window.DASHBOARD_DATA.
data.js           lo genera build_data.py. El versionado está vacío a propósito.
build_data.py     orquesta: lee cada fuente, agrega y escribe data.js.
serve.py          sirve la carpeta + /regenerar y /salud.
fuentes/
  base.py         semanas, agregación y el formato del evento. No sabe de fuentes.
  leia.py         SQLite de LeIA        -> consultas
  gdp.py          Postgres de GDP       -> consultas
  analyst.py      AgentCore + Cognito   -> consultas  (Agente CS)
```

El corte es ese: **una fuente sabe de su origen y de nada más**, y devuelve
siempre lo mismo:

```python
{"usuario": "czelada", "cuando": datetime(hora Lima)}
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
| `/regenerar` | relee las fuentes y reescribe `data.js`. Es el botón «Actualizar» |
| `/salud`     | si responde la fuente de cada agente, y si hay `data.js` |

```bash
make salud     # curl /salud formateado
```

---

Analítica Avanzada & AI · Prestamype Holding
