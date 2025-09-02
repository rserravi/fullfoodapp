from __future__ import annotations
from typing import Any

def call_azure_openai(prompt: str, client: Any, model: str) -> str:
    """Call Azure OpenAI ``responses.create`` and return the first text.

    Parameters
    ----------
    prompt: str
        Prompt to send to the model.
    client: Any
        Azure OpenAI client (must provide ``responses.create``).
    model: str
        Model identifier.

    Returns
    -------
    str
        Extracted text from the first output content.

    Raises
    ------
    ValueError
        If the response structure is unexpected.
    """
    resp = client.responses.create(model=model, input=prompt)
    try:
        return resp.output[0].content[0].text
    except (AttributeError, IndexError, KeyError, TypeError):
        raise ValueError("Respuesta inválida de Azure OpenAI")
