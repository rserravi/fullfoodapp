import pytest

from api.config import settings

pytestmark = pytest.mark.integration

def test_integration_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"

@pytest.mark.skipif(
    not settings.azure_openai_embedding_deployment or "example" in settings.azure_openai_endpoint,
    reason="Azure OpenAI no configurado",
)
def test_integration_search_embedding(client):
    vec = next(iter(settings.parsed_vector_dims().keys()), None)
    payload = {"query": "zucchini bell peppers roast", "top_k": 1, "vector": vec}
    r = client.post("/rag/search", json=payload)
    assert r.status_code == 200, r.text
    hits = r.json().get("hits", [])
    assert len(hits) >= 1, "No devolvió resultados; verifica que la ingesta se ejecutó y Qdrant está arriba."
