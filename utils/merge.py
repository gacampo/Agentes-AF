"""Fusión determinística de documentos para el modo lite (refresh).

Cuando un agente corre en modo lite, solo reescribe una porción de su
documento anterior (ej. la Fase B del Agente 7, o las secciones 8-9 del
Agente 8). Esto arma el documento final combinando texto viejo + texto nuevo
por posición de heading — es código puro, no depende del LLM para "pegar"
bien las partes.
"""

from __future__ import annotations

import re


def _find_heading(text: str, pattern: str) -> re.Match | None:
    return re.search(pattern, text, re.IGNORECASE | re.MULTILINE)


def extract_section(text: str, start_pattern: str, end_pattern: str | None = None) -> str:
    """Extrae el tramo de `text` entre start_pattern y end_pattern (o hasta el
    final si end_pattern es None). Si no encuentra start_pattern, retorna el
    texto completo — fallback seguro: mejor pasar de más que perder contexto
    al armar el prompt de un refresh."""
    start_match = _find_heading(text, start_pattern)
    if not start_match:
        return text
    rest = text[start_match.start():]
    if end_pattern:
        end_match = _find_heading(rest, end_pattern)
        if end_match:
            return rest[: end_match.start()]
    return rest


def merge_lite_into_full(
    previous_full: str,
    lite_output: str,
    start_pattern: str,
    end_pattern: str | None = None,
) -> tuple[str, bool]:
    """Reemplaza, dentro de `previous_full`, el tramo entre `start_pattern` y
    `end_pattern` (o hasta el final si `end_pattern` es None) por `lite_output`.

    - Todo lo ANTES de start_pattern se conserva tal cual (ej. Fase A, o
      secciones 1-7 de la tesis).
    - Todo lo DESPUÉS de end_pattern se conserva tal cual (ej. Fase C si no
      cambió, o la sección 10 de riesgos).
    - Lo que está entre ambos se descarta y se reemplaza por `lite_output`.

    Retorna (documento_fusionado, merge_exitoso). Si no se pudo ubicar
    start_pattern en el documento anterior, hace un fallback seguro:
    concatena el refresh al final con una advertencia visible en vez de
    fallar o perder contenido — y devuelve merge_exitoso=False para que el
    llamador pueda loguear/alertar.
    """
    start_match = _find_heading(previous_full, start_pattern)
    if not start_match:
        fallback = (
            previous_full.rstrip()
            + "\n\n---\n\n"
            + "> ⚠️ **Fusión automática no pudo ubicar el punto de reemplazo** "
              "(heading esperado no encontrado en el documento anterior). "
              "El refresh se agregó al final — revisar y fusionar a mano.\n\n"
            + lite_output.strip()
            + "\n"
        )
        return fallback, False

    prefix = previous_full[: start_match.start()]

    suffix = ""
    if end_pattern:
        rest = previous_full[start_match.start():]
        end_match = _find_heading(rest, end_pattern)
        if end_match:
            suffix = rest[end_match.start():]

    merged = prefix.rstrip() + "\n\n" + lite_output.strip() + "\n\n" + suffix.lstrip()
    return merged, True


# Patrones de heading que usan los agentes 7 y 8 (deben coincidir con los
# headings literales que sus system prompts (full y lite) están instruidos
# a producir).
A7_FASE_B_PATTERN = r"^##\s*FASE\s*B"
A7_FASE_C_PATTERN = r"^##\s*FASE\s*C"

A8_SECCION_8_PATTERN = r"^##\s*8\."
A8_SECCION_10_PATTERN = r"^##\s*10\."
