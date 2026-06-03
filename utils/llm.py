"""Cliente LLM compartido para todos los agentes."""

from __future__ import annotations

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
    """Envía un prompt al modelo y retorna la respuesta como texto."""
    client = get_client()

    # Construir contenido del mensaje de usuario
    if cached_context:
        user_content = cached_context + "\n\n" + user_prompt
    else:
        user_content = user_prompt

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    usage = message.usage
    print(
        f"[tokens] model={model} "
        f"input={usage.input_tokens} output={usage.output_tokens}"
    )

    return message.content[0].text
