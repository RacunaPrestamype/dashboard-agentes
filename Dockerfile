# Tablero de uso de los agentes (HTML estático + serve.py).
# Sirve index.html/data.js y expone /regenerar, que corre build_data.py y
# reconstruye data.js leyendo la fuente de cada agente en solo lectura.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# sqlite3 (LeIA) viene en la stdlib; el driver de Postgres (GDP) y boto3
# (Analyst) no.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY index.html data.js build_data.py serve.py ./
COPY fuentes/ ./fuentes/
# Opcional: el mapeo a mano actorId -> nombre del Analyst Agent. El corchete
# hace que el COPY no falle si el archivo no existe.
COPY actors_map.jso[n] ./

ENV HOST=0.0.0.0 \
    PORT=8080 \
    LEIA_DB_PATH=/datos/leia/gestora.db \
    HOME=/tmp

# Usuario sin privilegios por defecto. El único archivo que este proceso
# escribe es data.js, y va con permiso de escritura para todos a propósito:
# así el contenedor puede correr con el uid que haga falta —el del host, para
# poder leer un ~/.aws montado— sin tener que reconstruir la imagen.
RUN useradd --create-home --uid 10003 tablero \
 && chown -R tablero:tablero /srv \
 && chmod 0666 /srv/data.js
USER tablero

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/salud',timeout=4).status==200 else 1)"

CMD ["python", "serve.py"]
