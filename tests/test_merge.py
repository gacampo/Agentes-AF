"""Tests de utils/merge.py: fusión determinística de documentos en modo lite."""

from __future__ import annotations

from utils.merge import (
    A7_FASE_B_PATTERN,
    A7_FASE_C_PATTERN,
    A8_SECCION_8_PATTERN,
    A8_SECCION_10_PATTERN,
    extract_section,
    merge_lite_into_full,
)

PREVIOUS_A7 = """## FASE A: RESUMEN INTEGRAL CONSOLIDADO

Resumen ejecutivo viejo...

## FASE B: MÉTRICAS FUNDAMENTALES

| ROIC | 18% |

## FASE C: MÉTODO DE VALORACIÓN

DCF con WACC 9%..."""

LITE_A7 = """## FASE B: MÉTRICAS FUNDAMENTALES

| ROIC | 24% |

## Ajuste al método de valoración

Sin cambios al método de valoración."""

PREVIOUS_A8 = """## 7. Calidad financiera y ajustes

Texto viejo de la seccion 7...

## 8. Tres escenarios...

Escenarios viejos con TIR 5%...

## 9. Conclusion

Rating viejo: 6.5/10

## 10. Riesgos principales a vigilar

Riesgo A, riesgo B..."""

LITE_A8 = """## 8. Tres escenarios...

Escenarios nuevos con TIR 9%...

## 9. Conclusion

Rating nuevo: 7.8/10"""


def test_merge_a7_preserva_fase_a_y_c_reemplaza_fase_b():
    merged, ok = merge_lite_into_full(PREVIOUS_A7, LITE_A7, A7_FASE_B_PATTERN, A7_FASE_C_PATTERN)
    assert ok
    assert "Resumen ejecutivo viejo" in merged
    assert "ROIC | 24%" in merged
    assert "ROIC | 18%" not in merged
    assert "DCF con WACC 9%" in merged


def test_merge_a8_preserva_1_7_y_10_reemplaza_8_9():
    merged, ok = merge_lite_into_full(PREVIOUS_A8, LITE_A8, A8_SECCION_8_PATTERN, A8_SECCION_10_PATTERN)
    assert ok
    assert "Texto viejo de la seccion 7" in merged
    assert "TIR 9%" in merged and "TIR 5%" not in merged
    assert "Riesgo A, riesgo B" in merged


def test_merge_fallback_cuando_no_encuentra_heading_no_pierde_contenido():
    previous_sin_headings = "Un documento viejo sin los headings esperados."
    merged, ok = merge_lite_into_full(previous_sin_headings, "Contenido nuevo", A7_FASE_B_PATTERN, A7_FASE_C_PATTERN)
    assert not ok
    assert "no pudo ubicar" in merged
    assert "Un documento viejo" in merged
    assert "Contenido nuevo" in merged


def test_extract_section_devuelve_el_tramo_esperado():
    fase_b = extract_section(PREVIOUS_A7, A7_FASE_B_PATTERN, A7_FASE_C_PATTERN)
    assert "ROIC | 18%" in fase_b
    assert "DCF con WACC 9%" not in fase_b
    assert "Resumen ejecutivo viejo" not in fase_b


def test_extract_section_sin_match_retorna_todo_el_texto():
    assert extract_section("texto sin headings", A7_FASE_B_PATTERN) == "texto sin headings"
