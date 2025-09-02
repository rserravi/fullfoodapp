import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from api.azure_openai import call_azure_openai


def _fake_response(text):
    return SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(text=text)])])


def test_call_azure_openai_parses_text():
    client = Mock()
    client.responses.create.return_value = _fake_response("hola")
    out = call_azure_openai("prompt", client, "gpt-4o-mini")
    assert out == "hola"
    client.responses.create.assert_called_once_with(model="gpt-4o-mini", input="prompt")


def test_call_azure_openai_bad_response():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(output=[])
    with pytest.raises(ValueError):
        call_azure_openai("prompt", client, "gpt-4o-mini")
