"""Tests de main.py:check_triggers (Delta Detector). yfinance está mockeado
— no hace llamadas de red reales, ni siquiera en modo --deep (que además
mockea utils.llm.ask para no llamar a la API real)."""

from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from utils import history_db


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import main as main_module
    importlib.reload(main_module)
    return main_module


def _fake_yfinance(prices: dict[str, float]):
    """Arma un módulo yfinance falso: Ticker(x).fast_info['lastPrice'] = prices[x]."""
    fake_module = types.ModuleType("yfinance")

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        @property
        def fast_info(self):
            if self.ticker not in prices:
                raise ValueError(f"ticker desconocido: {self.ticker}")
            return {"lastPrice": prices[self.ticker]}

    fake_module.Ticker = FakeTicker
    return fake_module


def _seed(db_days_ago=10, precio_referencia=100.0, ticker="EMPA", company="Empresa A"):
    history_db.record_run(
        company, "full", ticker=ticker, sector="Tech", pais="USA",
        fecha="01-Ene-2026", precio_referencia=precio_referencia, rating_compuesto=7.0,
        decision_portafolio="INGRESA", alocacion_pct=5.0,
    )
    # created_at se graba como "ahora" — para simular una corrida vieja, la
    # reescribimos directamente en la fila insertada.
    conn = history_db._connect()
    fake_created = (datetime.now(timezone.utc) - timedelta(days=db_days_ago)).isoformat()
    conn.execute("UPDATE runs SET created_at = ? WHERE company = ?", (fake_created, company))
    conn.commit()
    conn.close()


def test_sin_historial_no_rompe(isolated_env, capsys):
    main = isolated_env
    resultados = main.check_triggers()
    assert resultados == []


def test_sin_trigger_cuando_precio_estable_y_corrida_reciente(isolated_env):
    main = isolated_env
    _seed(db_days_ago=5, precio_referencia=100.0)
    fake_yf = _fake_yfinance({"EMPA": 103.0})  # +3%, dentro del umbral de 20%

    with patch.dict(sys.modules, {"yfinance": fake_yf}):
        resultados = main.check_triggers(price_threshold_pct=20.0, days_threshold=95)

    assert len(resultados) == 1
    assert resultados[0]["trigger"] is False


def test_trigger_por_movimiento_de_precio(isolated_env):
    main = isolated_env
    _seed(db_days_ago=5, precio_referencia=100.0)
    fake_yf = _fake_yfinance({"EMPA": 130.0})  # +30%, supera el umbral de 20%

    with patch.dict(sys.modules, {"yfinance": fake_yf}):
        resultados = main.check_triggers(price_threshold_pct=20.0, days_threshold=95)

    assert resultados[0]["trigger"] is True
    assert any("precio movió" in m for m in resultados[0]["motivos"])


def test_trigger_por_tiempo_transcurrido(isolated_env):
    main = isolated_env
    _seed(db_days_ago=120, precio_referencia=100.0)  # más de 95 días
    fake_yf = _fake_yfinance({"EMPA": 101.0})  # precio estable

    with patch.dict(sys.modules, {"yfinance": fake_yf}):
        resultados = main.check_triggers(price_threshold_pct=20.0, days_threshold=95)

    assert resultados[0]["trigger"] is True
    assert any("días desde la última corrida" in m for m in resultados[0]["motivos"])


def test_ticker_desconocido_no_rompe_las_demas_empresas(isolated_env):
    main = isolated_env
    _seed(db_days_ago=5, precio_referencia=100.0, ticker="TICKER_INEXISTENTE", company="Empresa Rara")
    _seed(db_days_ago=5, precio_referencia=50.0, ticker="EMPB", company="Empresa B")
    fake_yf = _fake_yfinance({"EMPB": 51.0})  # solo tiene precio para EMPB

    with patch.dict(sys.modules, {"yfinance": fake_yf}):
        resultados = main.check_triggers(price_threshold_pct=20.0, days_threshold=95)

    assert len(resultados) == 2
    empresa_rara = next(r for r in resultados if r["company"] == "Empresa Rara")
    empresa_b = next(r for r in resultados if r["company"] == "Empresa B")
    assert empresa_rara["precio_actual"] is None  # falló, pero no rompió nada
    assert empresa_b["precio_actual"] == 51.0


def test_deep_agrega_flag_estructural_cuando_hay_trigger(isolated_env):
    main = isolated_env
    _seed(db_days_ago=5, precio_referencia=100.0)
    fake_yf = _fake_yfinance({"EMPA": 130.0})  # dispara trigger de precio

    with patch.dict(sys.modules, {"yfinance": fake_yf}), \
         patch("utils.llm.ask", return_value="🚩 Cambio de CEO detectado"):
        resultados = main.check_triggers(price_threshold_pct=20.0, days_threshold=95, deep=True)

    assert any("🚩" in m for m in resultados[0]["motivos"])


def test_deep_no_llama_al_llm_si_no_hay_trigger(isolated_env):
    """--deep no debe gastar tokens en empresas que ya están OK."""
    main = isolated_env
    _seed(db_days_ago=5, precio_referencia=100.0)
    fake_yf = _fake_yfinance({"EMPA": 101.0})  # sin trigger

    llm_mock = MagicMock(return_value="Sin novedades estructurales.")
    with patch.dict(sys.modules, {"yfinance": fake_yf}), patch("utils.llm.ask", llm_mock):
        main.check_triggers(price_threshold_pct=20.0, days_threshold=95, deep=True)

    llm_mock.assert_not_called()
