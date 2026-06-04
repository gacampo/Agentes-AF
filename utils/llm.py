"""Cliente LLM compartido para todos los agentes."""

from __future__ import annotations

import anthropic
from datetime import datetime, timezone
from pathlib import Path

TOKEN_LOG_FILE = "reportes/token_log.txt"


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

    Usa streaming para evitar el límite de timeout del SDK en respuestas largas.
    """
    client = get_client()

    # Construir contenido del mensaje de usuario
    if cached_context:
        user_content = cached_context + "\n\n" + user_prompt
    else:
        user_content = user_prompt

    text_chunks: list[str] = []
    input_tokens = 0
    output_tokens = 0

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        for text in stream.text_stream:
            text_chunks.append(text)
        final = stream.get_final_message()
        input_tokens = final.usage.input_tokens
        output_tokens = final.usage.output_tokens

    log_line = (
        f"[tokens] model={model} "
        f"input={input_tokens} output={output_tokens}"
    )
    print(log_line)

    try:
        log_path = Path(TOKEN_LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {log_line}\n")
    except Exception:
        pass

    return "".join(text_chunks)
