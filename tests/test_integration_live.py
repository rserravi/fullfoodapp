import pytest
from api.config import settings

pytestmark = pytest.mark.integration


def test_integration_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_integration_search_default(client):
    vector = settings.parsed_embedding_models()[0]
    payload = {"query": "zucchini bell peppers roast", "top_k": 1, "vector": vector}
    r = client.post("/search", json=payload)
    assert r.status_code == 200, r.text
    hits = r.json().get("hits", [])
    assert len(hits) >= 1, "No devolvió resultados; verifica que la ingesta se ejecutó y Qdrant está arriba."
