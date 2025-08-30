import sys
import types
from pathlib import Path
import importlib.metadata as importlib_metadata

import pytest

# Stub ``email_validator`` and its distribution metadata so that pydantic's
# ``EmailStr`` can be imported without the optional dependency installed.
mod = types.ModuleType("email_validator")


def _validate_email(email, *args, **kwargs):  # pragma: no cover - simple stub
    return types.SimpleNamespace(email=email, normalized=email, local_part=email)


mod.validate_email = _validate_email
mod.__version__ = "2.0.0"
sys.modules.setdefault("email_validator", mod)

_orig_version = importlib_metadata.version


def _fake_version(name):  # pragma: no cover - used only in tests
    if name == "email-validator":
        return "2.0.0"
    return _orig_version(name)


importlib_metadata.version = _fake_version
# Ensure project root on path for imports when executing from tests dir
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
