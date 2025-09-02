import pytest
from api.config import settings

from api.config import settings

pytestmark = pytest.mark.integration


def test_integration_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


@pytest.mark.skip("/search no disponible en el entorno de pruebas")
def test_integration_search_mxbai(client):
    # Busca en inglés para forzar el vector mxbai si se usara 'auto'
    payload = {"query": "zucchini bell peppers roast", "top_k": 1, "vector": "mxbai"}

    r = client.post("/search", json=payload)

    assert r.status_code == 200, r.text
    hits = r.json().get("hits", [])
    assert len(hits) >= 1, "No devolvió resultados; verifica que la ingesta se ejecutó y Qdrant está arriba."
