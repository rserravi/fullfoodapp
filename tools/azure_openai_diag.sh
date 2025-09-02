#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_OPENAI_ENDPOINT:?AZURE_OPENAI_ENDPOINT no está definido}"
: "${AZURE_OPENAI_API_KEY:?AZURE_OPENAI_API_KEY no está definido}"
: "${AZURE_OPENAI_EMBEDDING_DEPLOYMENT:?AZURE_OPENAI_EMBEDDING_DEPLOYMENT no está definido}"
API_VERSION="${AZURE_OPENAI_API_VERSION:-2024-06-01}"

echo "== Test Azure OpenAI embeddings endpoint =="
curl -s -o /dev/null -w "%{http_code}\n" \
  "${AZURE_OPENAI_ENDPOINT}/openai/deployments/${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}/embeddings?api-version=${API_VERSION}" \
  -H "api-key: ${AZURE_OPENAI_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"input": "hola"}' || true
echo
echo "Done."
