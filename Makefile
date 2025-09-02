SHELL := /bin/bash

# -------- Config ----------
PORT ?= 8000
ENV_FILE ?= .env
VENV := .venv
PY := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

# -------- Helpers ---------
define check_env
	@if [ ! -f "$(ENV_FILE)" ]; then \
	  echo "🟡 Falta $(ENV_FILE). Ejecuta: cp .env.example .env y ajusta valores"; \
	  exit 1; \
	fi
endef

# -------- Tareas ----------
.PHONY: help
help:
	@echo "FullFoodApp - Makefile"
	@echo
	@echo "Variables Azure OpenAI en .env: AZURE_OPENAI_ENDPOINT y AZURE_OPENAI_API_KEY"
	@echo
	@echo "Tareas principales:"
	@echo "  make up           -> Levanta Qdrant + venv + deps + arranca API (via bootstrap)"
	@echo "  make ingest       -> Ingesta semillas (via bootstrap)"
	@echo "  make health       -> GET /health en el puerto $(PORT)"
	@echo "  make down         -> Para Qdrant (docker compose down)"
	@echo
	@echo "Testing:"
	@echo "  make test         -> Ejecuta tests unitarios (excluye 'integration')"
	@echo "  make test-unit    -> Alias de 'make test'"
        @echo "  make test-integration -> Ejecuta solo tests marcados como 'integration' (requiere servicios externos)"

	@echo
	@echo "Extras:"
	@echo "  make venv         -> Crea venv e instala requirements (api + dev)"
	@echo "  make run          -> Arranca API local en $(PORT) (sin bootstrap)"
	@echo "  make qdrant-up    -> Solo Qdrant"
	@echo "  make qdrant-down  -> Para Qdrant"
	@echo "  make qdrant-logs  -> Logs de Qdrant"
	@echo "  make kill-port    -> Mata proceso que escuche en $(PORT)"
	@echo

# --- Ruta estándar: usar el bootstrap ---
.PHONY: up start
up start:
	@./bootstrap_local.sh start

.PHONY: ingest
ingest:
	@./bootstrap_local.sh ingest

.PHONY: health
health:
	@./bootstrap_local.sh health $(PORT)

.PHONY: down stop
down stop:
	@./bootstrap_local.sh down

# --- Alternativas sin bootstrap (por si prefieres ejecutar a pelo) ---
.PHONY: venv
venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@source $(VENV)/bin/activate && pip install -r api/requirements.txt -r requirements-dev.txt

.PHONY: run
run: venv
	$(check_env)
	@echo "🚀 API en http://127.0.0.1:$(PORT)"
	PYTHONPATH=. $(PY) -m uvicorn api.main:app --reload --port $(PORT)

.PHONY: qdrant-up
qdrant-up:
	docker compose up -d qdrant

.PHONY: qdrant-down
qdrant-down:
	docker compose down

.PHONY: qdrant-logs
qdrant-logs:
	docker logs -f qdrant

# --- Utilidades ---
.PHONY: kill-port
kill-port:
        @PID=$$(lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t || true); \
	if [[ -n "$$PID" ]]; then \
	  echo "🛑 Matando PID(s) $$PID en puerto $(PORT)"; \
	  kill $$PID || true; sleep 1; \
	  PID2=$$(lsof -nP -iTCP:$(PORT) -sTCP:LISTEN -t || true); \
	  [[ -n "$$PID2" ]] && kill -9 $$PID2 || true; \
	else \
	  echo "✅ Puerto $(PORT) libre"; \
	fi

# --- Tests ---
.PHONY: test
test: venv
	$(check_env)
	PYTHONPATH=. $(PYTEST) -m "not integration" -q

.PHONY: test-unit
test-unit: test

.PHONY: test-integration
test-integration: venv qdrant-up
        $(check_env)
        # Ingesta mínima antes de los tests de integración
        PYTHONPATH=. $(PY) -m api.ingest
        # Ejecuta solo los tests integration (requiere servicios externos reales)
        PYTHONPATH=. $(PYTEST) -m "integration" -q


.PHONY: db-upgrade db-downgrade openapi seed-dev seed-rag test-e2e

db-upgrade:
	. .venv/bin/activate && alembic upgrade head

db-downgrade:
	. .venv/bin/activate && alembic downgrade -1

openapi:
	PYTHONPATH=. .venv/bin/python tools/export_openapi.py

seed-dev:
	curl -s -X POST http://127.0.0.1:8000/admin/seed-catalog -H 'X-API-Key: demo123' | jq

seed-rag:
	curl -s -X POST http://127.0.0.1:8000/admin/seed-rag -H 'X-API-Key: demo123' | jq

test-e2e:
	PYTHONPATH=. .venv/bin/pytest tests/test_e2e_mvp.py -q

.PHONY: ingest-local

ingest-local:
	PYTHONPATH=. .venv/bin/python tools/ingest_local.py --root data --recreate

.PHONY: gen-recipes ingest-generated ingest
