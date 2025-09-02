import asyncio
import sys
import types

from api.routes.generate import _call_llm


def test_call_llm_uses_messages(monkeypatch):
    calls = {}

    async def fake_create(model, messages):
        calls["model"] = model
        calls["messages"] = messages
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))]
        )

    dummy_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=fake_create)
        )
    )

    openai_stub = types.SimpleNamespace(AsyncAzureOpenAI=lambda **kwargs: dummy_client)
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    result = asyncio.run(_call_llm("hola"))
    assert result == "ok"
    assert calls["messages"] == [{"role": "user", "content": "hola"}]
