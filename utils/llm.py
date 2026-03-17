"""Cliente LLM compartido para todos los agentes."""

import os

import anthropic


def get_client() -> anthropic.Anthropic:
    """Retorna un cliente Anthropic configurado."""
    return anthropic.Anthropic()


def ask(system_prompt: str, user_prompt: str, model: str = "claude-sonnet-4-20250514", max_tokens: int = 8192) -> str:
    """Envía un prompt al modelo y retorna la respuesta como texto."""
    client = get_client()
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text
