"""Tests de integración de main.py: orquestación full, refresh lite, fusión
de documentos, y el enganche opcional del Agente 11 (Pabrai). Todo con el
LLM mockeado vía ScriptedAsk (ver conftest.py) — no llama a la API real."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import patch

import openpyxl
import pytest

from tests.conftest import contains, extract_requested_ids


QUALITATIVE_AGENTS = [
    "Business Model Clarifier",
    "Leadership & Capital Allocation",
    "Competitive Advantages Dynamics",
    "Customer Value & Durability",
    "Multidisciplinary Thinking",
]


def _build_core_rules(scripted_ask):
    """Reglas comunes para los agentes 7, 8, 9 y 10 — usadas en casi todos los
    tests de este archivo. Los agentes 1,2,3,5,6 caen en el catch-all."""

    a7_lite = contains("Organizador Principal", "REFRESH TRIMESTRAL")
    a7_full = contains("FASE A", "FASE B", "FASE C")
    scripted_ask.add(
        a7_lite,
        "## FASE B: MÉTRICAS FUNDAMENTALES\n\n| ROIC | 30% (nuevo) |\n\n"
        "```json\n{\"metricas\": [{\"metrica\": \"ROIC\", \"valor_actual\": 30.0, \"unidad\": \"%\", "
        "\"direccion\": \"mayor_mejor\", \"umbral\": 15.0, \"cumple\": true}]}\n```\n\n"
        "## Ajuste al método de valoración\n\nSin cambios.",
    )
    scripted_ask.add(
        a7_full,
        "## FASE A: RESUMEN INTEGRAL CONSOLIDADO\n\nResumen ejecutivo full ORIGINAL.\n\n"
        "## FASE B: MÉTRICAS FUNDAMENTALES\n\n| ROIC | 20% (original) |\n\n"
        "```json\n{\"metricas\": [{\"metrica\": \"ROIC\", \"valor_actual\": 20.0, \"unidad\": \"%\", "
        "\"direccion\": \"mayor_mejor\", \"umbral\": 15.0, \"cumple\": true}]}\n```\n\n"
        "## FASE C: MÉTODO DE VALORACIÓN\n\nDCF con WACC 9% ORIGINAL.",
    )

    a8_lite = contains("Scenario & Valuation Specialist", "REFRESH TRIMESTRAL")
    a8_full = contains("Scenario & Valuation Specialist")
    a8_json = (
        "```json\n{\"escenarios\": [{\"nombre\": \"base\", \"valor_intrinseco_5y\": 150, \"valor_intrinseco_10y\": 220, \"precio_actual\": 100, "
        "\"tir_5y_pct\": 8.4, \"tir_10y_pct\": 4.1}], \"rating\": {\"calidad_negocio\": 8, "
        "\"atractivo_valoracion\": 6, \"rating_compuesto\": 7.2, \"precio_referencia\": 100, "
        "\"fecha_rating\": \"10-Ago-2026\"}}\n```"
    )
    scripted_ask.add(a8_lite, "## 8. Tres escenarios...\n\nEscenarios NUEVOS.\n\n" + a8_json + "\n\n## 9. Conclusion\n\nRating NUEVO 7.2/10.")
    scripted_ask.add(
        a8_full,
        "## 7. Calidad financiera\n\nTexto original.\n\n## 8. Tres escenarios...\n\nEscenarios ORIGINALES.\n\n"
        + "```json\n{\"escenarios\": [{\"nombre\": \"base\", \"valor_intrinseco_5y\": 120, \"valor_intrinseco_10y\": 175, \"precio_actual\": 100, "
          "\"tir_5y_pct\": 3.7, \"tir_10y_pct\": 1.8}], \"rating\": {\"calidad_negocio\": 7, "
          "\"atractivo_valoracion\": 6, \"rating_compuesto\": 6.6, \"precio_referencia\": 100, "
          "\"fecha_rating\": \"01-Ene-2026\"}}\n```"
        + "\n\n## 9. Conclusion\n\nRating ORIGINAL 6.6/10.\n\n## 10. Riesgos principales a vigilar\n\nRiesgo histórico A, riesgo histórico B.",
    )

    scripted_ask.add(
        contains("Portfolio Manager"),
        "```json\n{\"decision\": \"INGRESA\", \"empresa\": \"Empresa Test\", \"ticker\": \"TST\", "
        "\"sector\": \"Tech\", \"pais\": \"USA\", \"alocacion_pct\": 5, \"descuento_fv_pct\": 20, "
        "\"portafolio_actualizado\": {\"posiciones\": [{\"empresa\": \"Empresa Test\", \"ticker\": \"TST\", "
        "\"sector\": \"Tech\", \"pais\": \"USA\", \"alocacion_pct\": 5, \"descuento_fv_pct\": 20}], "
        "\"cash_disponible_pct\": 95}}\n```",
    )
    scripted_ask.add(contains("QA Reviewer"), "QA OK — sin observaciones.")


def _add_catchall(scripted_ask):
    """SIEMPRE debe agregarse al final, después de cualquier otra regla —
    ScriptedAsk evalúa en orden, y esta matchea cualquier prompt."""
    scripted_ask.add(lambda sp: True, lambda sp, up, cc: f"Contenido genérico para: {sp[:40]}...")


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Aísla cada test en su propio directorio (portafolio.json relativo) y
    con una API key falsa (main.py la exige para arrancar, aunque no se use)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    import main as main_module
    importlib.reload(main_module)
    return main_module


def test_pipeline_full_genera_los_10_archivos_y_reporte_consolidado(isolated_env, scripted_ask, tmp_path):
    main = isolated_env
    _build_core_rules(scripted_ask)
    _add_catchall(scripted_ask)

    with patch("agents.base.ask", scripted_ask):
        results = main.run_analysis("Empresa Test", 100.0, "01-Ene-2026", "", output_dir="reportes_out", mode="full")

    base_path = tmp_path / "reportes_out" / "empresa_test"
    assert (base_path / "07_resumen_consolidado.md").exists()
    assert (base_path / "08_tesis_inversion.md").exists()
    assert (base_path / "09_portfolio_manager.md").exists()
    assert (base_path / "reporte_completo.md").exists()
    assert "ORIGINAL" in results["Organizador Principal"]
    assert "Pabrai Checklist" not in results  # no se pasó --pabrai-xlsx


def test_pipeline_lite_preserva_cualitativos_y_fusiona_numericos(isolated_env, scripted_ask, tmp_path):
    main = isolated_env
    _build_core_rules(scripted_ask)
    _add_catchall(scripted_ask)

    with patch("agents.base.ask", scripted_ask):
        results_full = main.run_analysis("Empresa Test", 100.0, "01-Ene-2026", "", output_dir="reportes_out", mode="full")
        results_lite = main.run_analysis(
            "Empresa Test", 110.0, "10-Ago-2026", "", output_dir="reportes_out", mode="lite",
            hecho_nuevo="Reportó Q2 con revenue +20%.",
        )

    for name in QUALITATIVE_AGENTS:
        assert results_lite[name] == results_full[name], f"{name} no debería cambiar en modo lite"

    a7 = results_lite["Organizador Principal"]
    assert "Resumen ejecutivo full ORIGINAL" in a7  # Fase A preservada
    assert "ROIC | 30% (nuevo)" in a7 and "ROIC | 20% (original)" not in a7  # Fase B actualizada
    assert "DCF con WACC 9% ORIGINAL" in a7  # Fase C preservada

    a8 = results_lite["El Consejo de los Especialistas"]
    assert a8.count("Texto original") == 1  # seccion 1-7 preservada, una sola vez
    assert "Escenarios NUEVOS" in a8 and "Escenarios ORIGINALES" not in a8
    assert a8.count("Riesgo histórico") == 1  # seccion 10 preservada, una sola vez

    a4 = results_lite["Primary Research Analyst"]
    assert "Investigación anterior (histórica)" in a4


def test_pipeline_lite_sin_full_previo_corta_con_systemexit(isolated_env, scripted_ask, tmp_path):
    main = isolated_env
    _build_core_rules(scripted_ask)
    _add_catchall(scripted_ask)

    with patch("agents.base.ask", scripted_ask):
        with pytest.raises(SystemExit):
            main.run_analysis("Empresa Nueva", 50.0, "10-Ago-2026", "", output_dir="reportes_out", mode="lite")


def test_pipeline_full_no_persiste_portafolio_si_a9_rompe_limites(isolated_env, scripted_ask, tmp_path):
    """Regresión de extremo a extremo: si el Agente 9 propone algo inválido,
    el pipeline entero sigue (no crashea) pero portafolio.json no se toca."""
    main = isolated_env
    a7_full = contains("FASE A", "FASE B", "FASE C")
    scripted_ask.add(a7_full, "## FASE A: R\n\nx\n\n## FASE B: MÉTRICAS FUNDAMENTALES\n\n```json\n{\"metricas\": []}\n```\n\n## FASE C: M\n\nx")
    scripted_ask.add(
        contains("Scenario & Valuation Specialist"),
        "## 8. E\n\nx\n\n```json\n{\"escenarios\": [{\"nombre\": \"base\", \"valor_intrinseco_5y\": 120, \"valor_intrinseco_10y\": 175, "
        "\"precio_actual\": 100, \"tir_5y_pct\": 3.7, \"tir_10y_pct\": 1.8}], \"rating\": {\"calidad_negocio\": 7, "
        "\"atractivo_valoracion\": 6, \"rating_compuesto\": 6.6, \"precio_referencia\": 100, \"fecha_rating\": \"x\"}}\n```"
        "\n\n## 9. C\n\nx\n\n## 10. R\n\nx",
    )
    scripted_ask.add(
        contains("Portfolio Manager"),
        # 15% > máximo de 10% por empresa -> debe bloquear
        "```json\n{\"decision\": \"INGRESA\", \"empresa\": \"X\", \"ticker\": \"X\", \"sector\": \"Tech\", "
        "\"pais\": \"USA\", \"alocacion_pct\": 15, \"descuento_fv_pct\": 20, \"portafolio_actualizado\": "
        "{\"posiciones\": [{\"empresa\": \"X\", \"ticker\": \"X\", \"sector\": \"Tech\", \"pais\": \"USA\", "
        "\"alocacion_pct\": 15, \"descuento_fv_pct\": 20}], \"cash_disponible_pct\": 85}}\n```",
    )
    scripted_ask.add(contains("QA Reviewer"), "QA OK.")
    _add_catchall(scripted_ask)

    with patch("agents.base.ask", scripted_ask):
        results = main.run_analysis("Empresa Riesgosa", 100.0, "01-Ene-2026", "", output_dir="reportes_out", mode="full")

    assert "🛑" in results["Portfolio Manager"]
    assert not (tmp_path / "reportes" / "portafolio.json").exists()
    # el resto del pipeline no se vio afectado
    assert "El Consejo de los Especialistas" in results
    assert "QA Reviewer" in results


# ═══════════════════════ Integración con el Agente 11 (Pabrai) ═══════════════════════

def _pabrai_rule(scripted_ask):
    def response(system_prompt, user_prompt, cached_context):
        ids = extract_requested_ids(cached_context or "")
        respuestas = [{"id": i, "veredicto": "OK", "severidad": "Menor", "notas": f"nota {i}"} for i in ids]
        return "```json\n" + json.dumps({"respuestas": respuestas}) + "\n```"

    scripted_ask.add(contains("Pabrai"), response)


def test_pipeline_full_con_pabrai_xlsx_crea_hoja_y_escribe_respuestas(
    isolated_env, scripted_ask, tmp_path, mini_pabrai_workbook
):
    main = isolated_env
    _build_core_rules(scripted_ask)
    _pabrai_rule(scripted_ask)
    _add_catchall(scripted_ask)

    with patch("agents.base.ask", scripted_ask):
        results = main.run_analysis(
            "Empresa Test", 100.0, "01-Ene-2026", "", output_dir="reportes_out", mode="full",
            pabrai_xlsx=str(mini_pabrai_workbook), pabrai_sheet="TESTCO",
        )

    assert "Pabrai Checklist" in results
    assert "9/9" in results["Pabrai Checklist"]
    wb = openpyxl.load_workbook(mini_pabrai_workbook)
    assert "TESTCO" in wb.sheetnames


def test_pipeline_lite_con_pabrai_xlsx_agrega_bloque_de_refresh(
    isolated_env, scripted_ask, tmp_path, mini_pabrai_workbook
):
    main = isolated_env
    _build_core_rules(scripted_ask)
    _pabrai_rule(scripted_ask)
    _add_catchall(scripted_ask)

    with patch("agents.base.ask", scripted_ask):
        main.run_analysis(
            "Empresa Test", 100.0, "01-Ene-2026", "", output_dir="reportes_out", mode="full",
            pabrai_xlsx=str(mini_pabrai_workbook), pabrai_sheet="TESTCO",
        )
        results2 = main.run_analysis(
            "Empresa Test", 110.0, "10-Ago-2026", "", output_dir="reportes_out", mode="lite",
            pabrai_xlsx=str(mini_pabrai_workbook), pabrai_sheet="TESTCO",
        )

    assert "Pabrai Checklist" in results2
    wb = openpyxl.load_workbook(mini_pabrai_workbook)
    ws = wb["TESTCO"]
    assert ws.cell(row=6, column=6).value is not None  # segundo bloque de columnas


def test_pipeline_sin_pabrai_xlsx_no_corre_el_agente_11(isolated_env, scripted_ask, tmp_path):
    main = isolated_env
    _build_core_rules(scripted_ask)
    _add_catchall(scripted_ask)

    with patch("agents.base.ask", scripted_ask):
        results = main.run_analysis("Empresa Sin Pabrai", 50.0, "01-Ene-2026", "", output_dir="reportes_out", mode="full")

    assert "Pabrai Checklist" not in results


def test_pipeline_lite_pabrai_sin_full_previo_omite_sin_crashear(
    isolated_env, scripted_ask, tmp_path, mini_pabrai_workbook
):
    main = isolated_env
    _build_core_rules(scripted_ask)
    _pabrai_rule(scripted_ask)
    _add_catchall(scripted_ask)

    with patch("agents.base.ask", scripted_ask):
        main.run_analysis("Empresa Base", 80.0, "01-Ene-2026", "", output_dir="reportes_out", mode="full")
        # Nota: nunca corrimos --pabrai-xlsx en el full, así que el refresh
        # del checklist no tiene de dónde partir.
        results = main.run_analysis(
            "Empresa Base", 85.0, "10-Ago-2026", "", output_dir="reportes_out", mode="lite",
            pabrai_xlsx=str(mini_pabrai_workbook), pabrai_sheet="NUEVA_SIN_FULL",
        )

    assert "Pabrai Checklist" not in results
    # el resto de la corrida lite igual se completó bien
    assert "El Consejo de los Especialistas" in results
