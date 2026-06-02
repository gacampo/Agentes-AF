"""Cliente LLM compartido para todos los agentes."""

from __future__ import annotations

import os

import anthropic


def get_client() -> anthropic.Anthropic:
    """Retorna un cliente Anthropic configurado."""
    return anthropic.Anthropic()


def ask(
    system_prompt: str,
    user_prompt: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 8192,
    cached_context: str | None = None,
) -> str:
    """Envía un prompt al modelo y retorna la respuesta como texto.

    El system_prompt y el cached_context (contexto acumulado de agentes previos)
    se marcan con cache_control ephemeral para reducir costos en llamadas sucesivas.
    """
    client = get_client()

    # System prompt como bloque cacheado (es grande y fijo por agente)
    system = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    # Contenido del mensaje de usuario: contexto cacheado + query actual
    if cached_context:
        user_content = [
            {"type": "text", "text": cached_context, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": user_prompt},
        ]
    else:
        user_content = [{"type": "text", "text": user_prompt}]

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )

    usage = message.usage
    cache_write = getattr(usage, "cache_creation_input_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    print(
        f"[tokens] model={model} "
        f"input={usage.input_tokens} output={usage.output_tokens} "
        f"cache_write={cache_write} cache_read={cache_read}"
    )

    return message.content[0].text
