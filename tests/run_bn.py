#!/usr/bin/env python3
"""Script de validación: corre el pipeline completo sobre Brookfield Corporation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import run_analysis

run_analysis(
    company="Brookfield Corporation",
    precio_actual=45.59,
    fecha_precio="2026-06-04",
    notas_corporativas="split 3-for-2 completado oct 2025; ~2.280M acciones post-split",
    output_dir="reportes",
    fresh=True,
)
