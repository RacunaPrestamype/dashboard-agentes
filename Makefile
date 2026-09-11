# Atajos del tablero. `make` sin argumentos lista lo que hay.
SHELL := /bin/bash
COMPOSE := docker compose
PUERTO ?= 8095

.DEFAULT_GOAL := ayuda

.PHONY: ayuda datos demo servir tablero tablero-datos salud
ayuda: ## esta lista
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

datos: ## regenera data.js leyendo las fuentes de los tres agentes
	python3 build_data.py

demo: ## regenera data.js con datos fabricados (sin tocar ninguna fuente)
	python3 build_data.py --demo

servir: ## levanta el tablero en local (PUERTO=8095 por defecto)
	@echo "http://localhost:$(PUERTO)"
	PORT=$(PUERTO) python3 serve.py

tablero: ## build + levanta el tablero en Docker
	$(COMPOSE) up -d --build
	@echo "http://localhost:$${PUERTO_TABLERO:-8095}"

tablero-datos: ## regenera data.js dentro del contenedor, sin reiniciarlo
	$(COMPOSE) exec dashboard python build_data.py

salud: ## qué fuente responde y cuál no
	@curl -s http://localhost:$${PUERTO_TABLERO:-$(PUERTO)}/salud | python3 -m json.tool
