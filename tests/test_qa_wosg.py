#!/usr/bin/env python3
"""Test de regresión: QAReviewer sobre tesis WOSG con errores conocidos."""

import sys
from pathlib import Path

# Asegurar que el root del proyecto esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.a10_qa_reviewer import QAReviewer

TESIS_PATH = Path(__file__).parent / "wosg_tesis_con_errores.md"


def main():
    tesis = TESIS_PATH.read_text(encoding="utf-8")

    print("=" * 70)
    print("TEST DE REGRESIÓN — Agente 10: QA Reviewer")
    print("Empresa: WOSG (Watches of Switzerland)")
    print("Tesis: con errores conocidos")
    print("=" * 70)
    print()

    agent = QAReviewer()
    reporte = agent.run(company="WOSG", context=tesis)

    print(reporte)
    print()
    print("=" * 70)
    print("TEST COMPLETADO")
    print("=" * 70)


if __name__ == "__main__":
    main()
