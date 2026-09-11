# Tablero de uso de los agentes (HTML estático + serve.py).
# Sirve index.html/data.js y expone /regenerar, que corre build_data.py y
# reconstruye data.js leyendo la base de cada agente en solo lectura.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# sqlite3 (LeIA) viene en la stdlib; el driver de Postgres (GDP) no.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY index.html data.js build_data.py serve.py ./
COPY fuentes/ ./fuentes/

ENV HOST=0.0.0.0 \
    PORT=8080 \
    LEIA_DB_PATH=/datos/leia/gestora.db

# Usuario sin privilegios. Escribe un solo archivo, /srv/data.js, y nada más.
RUN useradd --create-home --uid 10003 tablero && chown -R tablero:tablero /srv
USER tablero

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/salud',timeout=4).status==200 else 1)"

CMD ["python", "serve.py"]
