"""Tests del contrato full/lite de agents/base.py, usando el Agente 4
(Primary Research Analyst) como caso concreto de agente con soporte lite."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agents.a1_business_model import BusinessModelClarifier
from agents.a4_primary_research import PrimaryResearchAnalyst


def test_modo_full_usa_system_prompt_full_y_activa_web_search():
    captured = {}

    def fake_ask(system_prompt, user_prompt, model=None, max_tokens=None, cached_context=None, tools=None):
        captured.update(locals())
        return "RESPUESTA_FAKE"

    agente = PrimaryResearchAnalyst()
    with patch("agents.base.ask", fake_ask):
        out = agente.run("Mercado Libre", context={"__precio_mercado__": "PRECIO: 2340"})

    assert out == "RESPUESTA_FAKE"
    assert captured["system_prompt"] == agente.system_prompt
    assert "Compañía a analizar: **Mercado Libre**" in captured["user_prompt"]
    assert captured["tools"][0]["type"] == "web_search_20250305"
    assert captured["tools"][0]["max_uses"] == 8
    assert "PRECIO: 2340" in captured["cached_context"]


def test_modo_lite_usa_system_prompt_lite_e_incluye_previous_output():
    captured = {}

    def fake_ask(system_prompt, user_prompt, model=None, max_tokens=None, cached_context=None, tools=None):
        captured.update(locals())
        return "RESPUESTA_FAKE"

    agente = PrimaryResearchAnalyst()
    prev = "# Investigación anterior\n\nRevenue Q1: $5.000M..."
    with patch("agents.base.ask", fake_ask):
        out = agente.run(
            "Mercado Libre",
            context={"__hecho_nuevo__": "Reportó Q2: revenue +18% YoY, guidance elevado."},
            mode="lite",
            previous_output=prev,
        )

    assert out == "RESPUESTA_FAKE"
    assert captured["system_prompt"] == agente.system_prompt_lite
    assert prev in captured["user_prompt"]
    assert "Reportó Q2: revenue +18%" in captured["user_prompt"]
    assert captured["tools"][0]["max_uses"] == 8


def test_modo_lite_sin_previous_output_falla_con_error_claro():
    agente = PrimaryResearchAnalyst()
    with patch("agents.base.ask", lambda *a, **kw: "x"):
        with pytest.raises(ValueError, match="previous_output"):
            agente.run("Mercado Libre", mode="lite")


def test_agente_sin_soporte_lite_rechaza_el_modo():
    agente = BusinessModelClarifier()
    with patch("agents.base.ask", lambda *a, **kw: "x"):
        with pytest.raises(ValueError, match="no soporta modo lite"):
            agente.run("Mercado Libre", mode="lite", previous_output="x")


def test_modo_invalido_falla():
    agente = BusinessModelClarifier()
    with patch("agents.base.ask", lambda *a, **kw: "x"):
        with pytest.raises(ValueError, match="mode debe ser"):
            agente.run("Mercado Libre", mode="turbo")


def test_agente_sin_web_search_no_pasa_tools():
    captured = {}

    def fake_ask(system_prompt, user_prompt, model=None, max_tokens=None, cached_context=None, tools=None):
        captured["tools"] = tools
        return "x"

    agente = BusinessModelClarifier()
    with patch("agents.base.ask", fake_ask):
        agente.run("Mercado Libre")

    assert captured["tools"] is None
