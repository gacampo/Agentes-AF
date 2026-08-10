#!/usr/bin/env python3
"""Test de regresión: QAReviewer sobre tesis WOSG con errores conocidos.

Este es el único test "live" del repo: llama a la API real de Anthropic
(gasta tokens) y su salida se revisa a ojo, no con asserts automáticos —
sirve para chequear cualitativamente que el Agente 10 sigue detectando los
errores conocidos de la tesis WOSG después de cambios grandes al prompt.

Se excluye de la corrida default de pytest (ver `addopts` en pyproject.toml).
Correrlo explícitamente con: pytest -m live tests/test_qa_wosg.py -s
"""

import os
import sys
from pathlib import Path

import pytest

# Asegurar que el root del proyecto esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.a10_qa_reviewer import QAReviewer

TESIS_PATH = Path(__file__).parent / "wosg_tesis_con_errores.md"


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="requiere ANTHROPIC_API_KEY")
def test_qa_reviewer_detecta_errores_wosg():
    main()


def main():
    tesis = TESIS_PATH.read_text(encoding="utf-8")

    print("=" * 70)
    print("TEST DE REGRESIÓN — Agente 10: QA Reviewer")
    print("Empresa: WOSG (Watches of Switzerland)")
    print("Tesis: con errores conocidos")
    print("=" * 70)
    print()

    agent = QAReviewer()
    # El nuevo agente espera context como dict[str, str]; usamos una clave descriptiva
    reporte = agent.run(company="WOSG", context={"Tesis simulada (Agentes 1-5)": tesis})

    print(reporte)
    print()
    print("=" * 70)
    print("TEST COMPLETADO")
    print("=" * 70)


if __name__ == "__main__":
    main()
