"""Tests de utils/validation.py: los validadores puros, y cómo los agentes
7 (no bloqueante), 8 (no bloqueante) y 9 (BLOQUEANTE) los usan."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.validation import (
    extract_json_block,
    validate_metrics_json,
    validate_pabrai_answers,
    validate_portfolio_json,
    validate_scenarios_json,
)


# ═══════════════════════ extract_json_block ═══════════════════════

def test_extract_json_block_encuentra_el_ultimo_bloque():
    text = "texto\n```json\n{\"a\": 1}\n```\nmas texto\n```json\n{\"a\": 2}\n```"
    assert extract_json_block(text) == {"a": 2}


def test_extract_json_block_retorna_none_si_no_hay_bloque():
    assert extract_json_block("solo texto plano") is None


def test_extract_json_block_retorna_none_si_json_invalido():
    assert extract_json_block("```json\n{invalido\n```") is None


# ═══════════════════════ validate_metrics_json (Agente 7) ═══════════════════════

def test_metrics_json_consistente_no_da_issues():
    data = {"metricas": [
        {"metrica": "ROIC", "valor_actual": 24.3, "unidad": "%", "direccion": "mayor_mejor", "umbral": 15.0, "cumple": True},
        {"metrica": "Deuda neta/EBITDA", "valor_actual": 0.8, "unidad": "x", "direccion": "menor_mejor", "umbral": 2.0, "cumple": True},
    ]}
    assert validate_metrics_json(data) == []


def test_metrics_json_detecta_cumple_inconsistente_y_rango_implausible():
    data = {"metricas": [
        {"metrica": "ROIC", "valor_actual": 8.0, "unidad": "%", "direccion": "mayor_mejor", "umbral": 15.0, "cumple": True},
        {"metrica": "PER", "valor_actual": 900, "unidad": "x", "direccion": "menor_mejor", "umbral": 20.0, "cumple": True},
    ]}
    issues = validate_metrics_json(data)
    assert any("debería ser False" in i for i in issues)
    assert any("fuera de un rango plausible" in i for i in issues)


# ═══════════════════════ validate_scenarios_json (Agente 8) ═══════════════════════

def test_scenarios_json_tir_y_rating_consistentes():
    data = {
        "escenarios": [{"nombre": "base", "valor_intrinseco_5y": 150, "valor_intrinseco_10y": 220,
                         "precio_actual": 100, "tir_5y_pct": 8.4, "tir_10y_pct": 8.2}],
        "rating": {"calidad_negocio": 8.0, "atractivo_valoracion": 6.5, "rating_compuesto": 7.4,
                   "precio_referencia": 100, "fecha_rating": "10-Ago-2026"},
    }
    assert validate_scenarios_json(data) == []


def test_scenarios_json_detecta_tir_inflada_y_rating_mal_calculado():
    data = {
        "escenarios": [{"nombre": "base", "valor_intrinseco_5y": 150, "valor_intrinseco_10y": 220,
                         "precio_actual": 100, "tir_5y_pct": 45.0, "tir_10y_pct": 8.2}],
        "rating": {"calidad_negocio": 9.0, "atractivo_valoracion": 2.0, "rating_compuesto": 8.5,
                   "precio_referencia": 100, "fecha_rating": "10-Ago-2026"},
    }
    issues = validate_scenarios_json(data)
    assert any("TIR 5 años declarada" in i for i in issues)
    assert any("rating_compuesto declarado" in i for i in issues)


def test_scenarios_json_no_da_falso_positivo_con_valor_intrinseco_distinto_por_horizonte():
    """Regresión del hallazgo real en BRK.B: el escenario optimista tenía un
    valor intrínseco de 710 a 5 años y 1.210 a 10 años (proyección con
    crecimiento compuesto, no el mismo número dos veces). El schema viejo
    (un solo campo 'valor_intrinseco') comparaba la TIR a 10 años contra el
    valor del año 5 y disparaba un falso positivo. Con el campo separado,
    no debería marcar nada."""
    data = {
        "escenarios": [{
            "nombre": "optimista",
            "valor_intrinseco_5y": 710,
            "valor_intrinseco_10y": 1210,
            "precio_actual": 521.80,
            "tir_5y_pct": 8.5,   # implícita ~6.4% + recompras ~2% ≈ declarada, dentro de tolerancia
            "tir_10y_pct": 10.5,  # implícita ~8.8% + recompras ≈ declarada, dentro de tolerancia
        }],
        "rating": {"calidad_negocio": 8.5, "atractivo_valoracion": 5.5, "rating_compuesto": 7.3,
                   "precio_referencia": 521.80, "fecha_rating": "09-Aug-2026"},
    }
    assert validate_scenarios_json(data) == []


# ═══════════════════════ validate_portfolio_json (Agente 9, bloqueante) ═══════════════════════

REGLAS = {"max_por_empresa_pct": 10.0, "max_por_sector_pct": 25.0, "max_por_pais_pct": 25.0, "min_posicion_pct": 1.0}


def test_portfolio_json_valido_sin_issues():
    data = {
        "decision": "INGRESA", "alocacion_pct": 6,
        "portafolio_actualizado": {
            "posiciones": [{"empresa": "X", "sector": "Consumo", "pais": "USA", "alocacion_pct": 6}],
            "cash_disponible_pct": 94,
        },
    }
    assert validate_portfolio_json(data, REGLAS) == []


def test_portfolio_json_detecta_exceso_por_empresa():
    data = {
        "decision": "INGRESA", "alocacion_pct": 15,
        "portafolio_actualizado": {
            "posiciones": [{"empresa": "X", "sector": "Consumo", "pais": "USA", "alocacion_pct": 15}],
            "cash_disponible_pct": 85,
        },
    }
    issues = validate_portfolio_json(data, REGLAS)
    assert any("supera el máximo por empresa" in i for i in issues)


def test_portfolio_json_detecta_que_no_cierra_en_100():
    data = {
        "decision": "INGRESA", "alocacion_pct": 5,
        "portafolio_actualizado": {
            "posiciones": [{"empresa": "X", "sector": "Salud", "pais": "Argentina", "alocacion_pct": 5}],
            "cash_disponible_pct": 80,
        },
    }
    issues = validate_portfolio_json(data, REGLAS)
    assert any("no cierra en 100%" in i for i in issues)


def test_portfolio_json_detecta_concentracion_de_sector():
    data = {
        "decision": "INGRESA", "alocacion_pct": 8,
        "portafolio_actualizado": {
            "posiciones": [
                {"empresa": "A", "sector": "Consumo", "pais": "Brasil", "alocacion_pct": 10},
                {"empresa": "B", "sector": "Consumo", "pais": "Brasil", "alocacion_pct": 9},
                {"empresa": "Z", "sector": "Consumo", "pais": "Brasil", "alocacion_pct": 8},
            ],
            "cash_disponible_pct": 73,
        },
    }
    issues = validate_portfolio_json(data, REGLAS)
    assert any("Sector 'Consumo'" in i and "supera el máximo" in i for i in issues)


# ═══════════════════════ validate_pabrai_answers (Agente 11) ═══════════════════════

def test_pabrai_answers_completas_sin_issues():
    data = {"respuestas": [
        {"id": 1, "veredicto": "OK", "severidad": "Menor", "notas": "evidencia 1"},
        {"id": 2, "veredicto": "⚠️ Red Flag", "severidad": "Moderado", "notas": "evidencia 2"},
    ]}
    assert validate_pabrai_answers(data, expected_ids={1, 2}) == []


def test_pabrai_answers_detecta_faltantes_y_veredicto_invalido():
    data = {"respuestas": [
        {"id": 1, "veredicto": "MAS O MENOS", "severidad": "Menor", "notas": "x"},
    ]}
    issues = validate_pabrai_answers(data, expected_ids={1, 2, 3})
    assert any("no es uno de" in i for i in issues)
    assert any("Faltan 2 pregunta" in i for i in issues)


# ═══════════════════════ Wiring a nivel agente: 7 y 8 no bloqueantes, 9 bloqueante ═══════════════════════

def test_agente7_anota_warning_visible_pero_no_bloquea():
    from agents.a7_organizer import OrganizadorPrincipal

    fake_bad = (
        "## FASE B\n\n```json\n"
        '{"metricas": [{"metrica": "ROIC", "valor_actual": 8.0, "unidad": "%", '
        '"direccion": "mayor_mejor", "umbral": 15.0, "cumple": true}]}'
        "\n```"
    )
    with patch("agents.base.ask", lambda *a, **kw: fake_bad):
        out = OrganizadorPrincipal().run("Empresa X", context={"algo": "y"})

    assert "⚠️" in out
    assert "ROIC" in out


def test_agente8_anota_warning_visible_pero_no_bloquea():
    from agents.a8_council import ConsejoDeEspecialistas

    fake_bad = (
        "## 8. Escenarios\n\n```json\n"
        '{"escenarios": [{"nombre": "base", "valor_intrinseco_5y": 150, "valor_intrinseco_10y": 220, "precio_actual": 100, '
        '"tir_5y_pct": 45.0, "tir_10y_pct": 4.1}], "rating": {"calidad_negocio": 9, '
        '"atractivo_valoracion": 2, "rating_compuesto": 8.5, "precio_referencia": 100, "fecha_rating": "x"}}'
        "\n```"
    )
    with patch("agents.base.ask", lambda *a, **kw: fake_bad):
        out = ConsejoDeEspecialistas().run("Empresa X", context={"algo": "y"})

    assert "⚠️" in out


def test_agente9_bloquea_y_no_persiste_si_rompe_limites(tmp_path, monkeypatch):
    from agents import a9_portfolio_manager as a9mod

    # PORTFOLIO_FILE ("reportes/portafolio.json") es un default de función
    # fijado al importar el módulo, así que monkeypatchear el atributo del
    # módulo no alcanza — nos movemos a un directorio limpio en su lugar,
    # ya que el path es relativo.
    monkeypatch.chdir(tmp_path)
    portfolio_file = tmp_path / a9mod.PORTFOLIO_FILE

    fake_bad = (
        "```json\n"
        '{"decision": "INGRESA", "empresa": "X", "ticker": "X", "sector": "Tech", "pais": "USA", '
        '"alocacion_pct": 15, "descuento_fv_pct": 20, "portafolio_actualizado": '
        '{"posiciones": [{"empresa": "X", "ticker": "X", "sector": "Tech", "pais": "USA", '
        '"alocacion_pct": 15, "descuento_fv_pct": 20}], "cash_disponible_pct": 85}}'
        "\n```"
    )
    with patch("agents.base.ask", lambda *a, **kw: fake_bad):
        out = a9mod.PortfolioManager().run("Empresa X", context={"algo": "y"})

    assert "🛑" in out
    assert "supera el máximo por empresa" in out
    assert not portfolio_file.exists()


def test_agente9_persiste_cuando_la_alocacion_es_valida(tmp_path, monkeypatch):
    from agents import a9_portfolio_manager as a9mod

    monkeypatch.chdir(tmp_path)
    portfolio_file = tmp_path / a9mod.PORTFOLIO_FILE

    fake_ok = (
        "```json\n"
        '{"decision": "INGRESA", "empresa": "X", "ticker": "X", "sector": "Tech", "pais": "USA", '
        '"alocacion_pct": 6, "descuento_fv_pct": 20, "portafolio_actualizado": '
        '{"posiciones": [{"empresa": "X", "ticker": "X", "sector": "Tech", "pais": "USA", '
        '"alocacion_pct": 6, "descuento_fv_pct": 20}], "cash_disponible_pct": 94}}'
        "\n```"
    )
    with patch("agents.base.ask", lambda *a, **kw: fake_ok):
        out = a9mod.PortfolioManager().run("Empresa X", context={"algo": "y"})

    assert "Portafolio actualizado" in out
    assert portfolio_file.exists()
    saved = json.loads(portfolio_file.read_text())
    assert saved["posiciones"][0]["alocacion_pct"] == 6
    # regresión del bug real que encontramos: 'reglas' debe preservarse
    assert saved["reglas"]["max_por_empresa_pct"] == 10.0
