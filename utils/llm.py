"""Cliente LLM compartido para todos los agentes.

Incluye:
- Soporte de tools (web search en vivo) via el parámetro `tools`.
- Prompt caching real (cache_control) sobre el contexto acumulado.
- Reintentos con backoff exponencial ante errores transitorios de la API.
- Logging de tokens, cache hits y búsquedas web usadas (para trackear costo).
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

TOKEN_LOG_FILE = "reportes/token_log.txt"

# Web search tool server-side de Anthropic. Confirmar el string de versión
# vigente contra la doc (platform.claude.com/docs) antes de desplegar: puede
# cambiar con el tiempo (ej. web_search_20250305 -> versiones más nuevas).
WEB_SEARCH_TOOL_VERSION = "web_search_20250305"

# Errores transitorios: vale la pena reintentar (problemas de red, rate limit,
# sobrecarga momentánea del servicio). Errores 4xx de request inválido o auth
# NO se reintentan porque van a fallar siempre igual.
RETRYABLE_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
    anthropic.RateLimitError,
    anthropic.OverloadedError,
)

DEFAULT_MAX_RETRIES = 4
DEFAULT_BASE_DELAY = 2.0  # segundos, se duplica en cada intento + jitter


def get_client() -> anthropic.Anthropic:
    """Retorna un cliente Anthropic configurado."""
    return anthropic.Anthropic()


def web_search_tool(max_uses: int = 6, allowed_domains: list[str] | None = None) -> list[dict]:
    """Arma la definición del tool de web search para pasarle a `ask()`.

    Uso típico en un agente:
        tools = web_search_tool(max_uses=6)
        ask(..., tools=tools)
    """
    tool: dict = {
        "type": WEB_SEARCH_TOOL_VERSION,
        "name": "web_search",
        "max_uses": max_uses,
    }
    if allowed_domains:
        tool["allowed_domains"] = allowed_domains
    return [tool]


def _log_usage(model: str, final_message, extra: str = "") -> None:
    """Loguea tokens, cache hits/writes y búsquedas web usadas en esta llamada."""
    usage = final_message.usage
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0

    server_tool_use = getattr(usage, "server_tool_use", None)
    n_searches = getattr(server_tool_use, "web_search_requests", 0) if server_tool_use else 0

    log_line = (
        f"[tokens] model={model} input={input_tokens} output={output_tokens} "
        f"cache_read={cache_read} cache_write={cache_write} web_searches={n_searches}"
        + (f" {extra}" if extra else "")
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


def ask(
    system_prompt: str,
    user_prompt: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 8192,
    cached_context: str | None = None,
    tools: list[dict] | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """Envía un prompt al modelo y retorna la respuesta como texto.

    Usa streaming para evitar el límite de timeout del SDK en respuestas largas.

    - Si se pasa `cached_context`, se envía como un bloque de contenido separado
      marcado con cache_control (ephemeral). Como el contexto crece agente a
      agente dentro de una misma corrida, esto permite que cada llamada
      posterior reutilice (a 10% del costo) el prefijo ya cacheado por la
      llamada anterior, en vez de pagar tokens de input completos cada vez.
    - Si se pasa `tools`, se habilitan server-side tools (ej. web search) —
      Anthropic ejecuta las búsquedas y devuelve la respuesta ya sintetizada
      dentro del mismo streaming, sin loops adicionales de este lado.
    - Reintenta automáticamente ante errores transitorios (red, rate limit,
      sobrecarga) con backoff exponencial + jitter. Errores de request
      inválido o autenticación se propagan de inmediato sin reintentar.
    """
    client = get_client()

    if cached_context:
        user_content = [
            {
                "type": "text",
                "text": cached_context,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": user_prompt},
        ]
    else:
        user_content = user_prompt

    stream_kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    if tools:
        stream_kwargs["tools"] = tools

    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            text_chunks: list[str] = []
            with client.messages.stream(**stream_kwargs) as stream:
                for text in stream.text_stream:
                    text_chunks.append(text)
                final = stream.get_final_message()

            extra = f"attempt={attempt}" if attempt > 1 else ""
            _log_usage(model, final, extra=extra)
            return "".join(text_chunks)

        except RETRYABLE_ERRORS as e:
            last_error = e
            if attempt == max_retries:
                break
            delay = DEFAULT_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(
                f"[retry] {type(e).__name__} en intento {attempt}/{max_retries}: {e}. "
                f"Reintentando en {delay:.1f}s..."
            )
            time.sleep(delay)

        except anthropic.APIStatusError:
            # Errores 4xx no transitorios (auth, request inválido, etc): no
            # tiene sentido reintentar, van a fallar siempre igual.
            raise

    raise RuntimeError(
        f"ask() falló después de {max_retries} intentos. Último error: {last_error}"
    ) from last_error
