import pytest
from fastapi.testclient import TestClient
import api.main as main

@pytest.fixture
def client(request, monkeypatch):
    """
    - Para tests unitarios (sin marker 'integration'): no tocamos Qdrant/Ollama en startup.
    - Para tests de integración: usamos el startup real (Qdrant/Ollama).
    """
    is_integration = any(m.name == "integration" for m in request.node.iter_markers())
    if not is_integration:
        async def noop(*args, **kwargs):  # pragma: no cover
            return None
        monkeypatch.setattr(main, "ensure_collection", noop)
    return TestClient(main.app)
