#!/usr/bin/env bash
set -euo pipefail
echo "== Ollama version =="
ollama --version || true
echo "== Test /api/embeddings =="
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:11434/api/embeddings || true
echo "== Test mxbai-embed-large on /api/embeddings =="
curl -s http://localhost:11434/api/embeddings -d '{ "model": "mxbai-embed-large", "prompt": "hola" }' || true
echo
echo "== Test mxbai-embed-large on /api/embed =="
curl -s http://localhost:11434/api/embed -d '{ "model": "mxbai-embed-large", "input": "hola" }' || true
echo
echo "Done."
