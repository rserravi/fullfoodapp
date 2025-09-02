import pytest
from api.config import settings
from api.rate_limit_store import store


def test_protected_endpoint_requires_token(monkeypatch, client):
    """Endpoints con dependencia de autenticación deben devolver 401 sin token."""
    monkeypatch.setattr(settings, "auth_fallback_user", None)
    resp = client.get("/catalog/products")
    assert resp.status_code == 401


def test_size_limit_middleware(client):
    """El middleware debe rechazar cuerpos que exceden el límite configurado."""
    big_body = "x" * (settings.max_body_bytes + 1)
    resp = client.post("/auth/login", data=big_body, headers={"Content-Type": "text/plain"})
    assert resp.status_code == 413


def test_rate_limit_middleware(client):
    """Al exceder el número de peticiones por ventana se debe obtener 429."""
    # Asegura que la pila de middlewares esté construida
    client.get("/health")
    from api.middleware.rate_limit import RateLimitMiddleware
    from api.rate_limit_store import store

    layer = client.app.middleware_stack
    while not isinstance(layer, RateLimitMiddleware):
        layer = layer.app
    layer.limit = layer.burst = 2

    store._local.clear()

    payload = {"email": "user@example.com", "dev_pin": "000000"}
    assert client.post("/auth/login", json=payload).status_code == 200
    assert client.post("/auth/login", json=payload).status_code == 200
    assert client.post("/auth/login", json=payload).status_code == 429

