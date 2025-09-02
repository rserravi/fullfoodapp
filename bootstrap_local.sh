#!/usr/bin/env bash
set -euo pipefail

# --- Config ---
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
PORT_DEFAULT="${PORT:-8000}"
ENV_FILE="${REPO_ROOT}/.env"

# --- Helpers ---
msg() { printf "\033[1;32m%s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m%s\033[0m\n" "$*"; }
err() { printf "\033[1;31m%s\033[0m\n" "$*" >&2; }

ensure_env_file() {
  if [[ -f "${ENV_FILE}" ]]; then
    msg "✅ .env encontrado"
    return
  fi
  warn "⚠️  No hay .env, creando uno por defecto…"
  cat > "${ENV_FILE}" <<'ENV'
# === LOG ===
LOG_LEVEL=INFO

# === Azure OpenAI ===
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2024-06-01
AZURE_OPENAI_CHAT_DEPLOYMENT=
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=
LLM_MODEL=llama3.1:8b
EMBEDDING_MODELS=mxbai-embed-large,jina/jina-embeddings-v2-base-es


# === Azure OpenAI (Embeddings) ===
AZURE_OPENAI_ENDPOINT=https://example-endpoint.openai.azure.com
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
EMBEDDING_MODELS=text-embedding-3-large

# === Qdrant (vector DB) ===
QDRANT_URL=http://localhost:6333
COLLECTION_NAME=recipes

# === Dimensiones de vectores (evitamos llamar al LLM en startup) ===
VECTOR_DIMS=mxbai:1024,jina:768


# === CORS (para frontend en V2) ===
CORS_ALLOW_ORIGINS=*
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=*
CORS_ALLOW_HEADERS=*
ENV
  msg "📝 .env generado"
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    err "Docker no está instalado/en PATH. Instálalo para levantar Qdrant."
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    err "Docker no está corriendo. Abre la app de Docker Desktop."
    exit 1
  fi
}

ensure_qdrant() {
  msg "⏫ Levantando Qdrant (Docker Compose)…"
  docker compose up -d qdrant
  msg "✅ Qdrant listo en http://localhost:6333"
}

ensure_venv() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    msg "🐍 Creando venv…"
    python3 -m venv "${VENV_DIR}"
  fi
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  msg "📦 Instalando dependencias…"
  pip install -r "${REPO_ROOT}/api/requirements.txt"
}

export_azure_openai_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC2046
    export $(grep -E '^AZURE_OPENAI_' "${ENV_FILE}" | xargs) || true
  else
    warn "⚠️  No se encontró ${ENV_FILE}; define AZURE_OPENAI_* manualmente."
  fi
}

free_port() {
  local p="$1"
  while lsof -nP -iTCP:"${p}" -sTCP:LISTEN >/dev/null 2>&1; do
    p=$((p+1))
  done
  echo "${p}"
}

start_api() {
  ensure_env_file
  ensure_docker
  ensure_qdrant
  ensure_venv
  export_azure_openai_env

  local port
  port="$(free_port "${PORT_DEFAULT}")"
  if [[ "${port}" != "${PORT_DEFAULT}" ]]; then
    warn "⚠️  Puerto ${PORT_DEFAULT} ocupado; usaré ${port}"
  fi
  msg "🚀 Arrancando API en http://127.0.0.1:${port}"
  PYTHONPATH="${REPO_ROOT}" \
  "${VENV_DIR}/bin/python" -m uvicorn api.main:app --reload --port "${port}"
}

ingest_seeds() {
  ensure_env_file
  ensure_venv
  export_azure_openai_env
  msg "📥 Ingestando semillas en Qdrant…"
  PYTHONPATH="${REPO_ROOT}" "${VENV_DIR}/bin/python" -m api.ingest
  msg "✅ Ingesta OK"
}

health() {
  local port="${1:-8000}"
  msg "🩺 Health check (puerto ${port})…"
  curl -s "http://127.0.0.1:${port}/health" | jq .
}

down_qdrant() {
  msg "🛑 Parando Qdrant…"
  docker compose down
}

case "${1:-}" in
  up|start)
    start_api
    ;;
  ingest)
    ingest_seeds
    ;;
  health)
    health "${2:-8000}"
    ;;
  down|stop)
    down_qdrant
    ;;
  *)
    cat <<USAGE
Usage: $(basename "$0") <command>

Commands:
  start|up        Levanta Qdrant, venv, deps y arranca la API (requiere AZURE_OPENAI_* en .env; puerto libre desde 8000)
  ingest          Ingesta las semillas en Qdrant (usa .env y venv)
  health [port]   Health check de la API (default: 8000)
  down|stop       Para Qdrant (docker compose down)

Ejemplos:
  ./bootstrap_local.sh start
  ./bootstrap_local.sh ingest
  ./bootstrap_local.sh health 8010
  ./bootstrap_local.sh down
USAGE
    ;;
esac