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
    log_line = (
        f"[tokens] model={model} "
        f"input={usage.input_tokens} output={usage.output_tokens}"
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

    return message.content[0].text
