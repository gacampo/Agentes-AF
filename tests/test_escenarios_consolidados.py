"""Tests de utils/escenarios_consolidados.py — el módulo que mantiene
reportes/escenarios_consolidados.json automáticamente al final de cada
corrida (ver main.py::run_analysis). No pega a la API real."""

from __future__ import annotations

import json

from utils.escenarios_consolidados import (
    load_escenarios,
    update_escenarios_consolidados,
)


def _a8_json(rating=7.5, precio=100.0):
    return (
        "## 8. Escenarios\n\n```json\n"
        + json.dumps({
            "escenarios": [
                {"nombre": "conservador", "valor_intrinseco_5y": 110, "valor_intrinseco_10y": 130, "precio_actual": precio, "tir_5y_pct": 2.0, "tir_10y_pct": 3.0},
                {"nombre": "base", "valor_intrinseco_5y": 160, "valor_intrinseco_10y": 220, "precio_actual": precio, "tir_5y_pct": 10.0, "tir_10y_pct": 8.0},
                {"nombre": "optimista", "valor_intrinseco_5y": 220, "valor_intrinseco_10y": 340, "precio_actual": precio, "tir_5y_pct": 17.0, "tir_10y_pct": 13.0},
            ],
            "rating": {
                "calidad_negocio": 8.0,
                "atractivo_valoracion": 6.5,
                "rating_compuesto": rating,
                "precio_referencia": precio,
                "fecha_rating": "13-Ago-2026",
            },
        })
        + "\n```\n"
    )


def _a9_json(ticker="TST", alocacion=5):
    return (
        "## Decisión\n\n```json\n"
        + json.dumps({
            "decision": "INGRESA",
            "empresa": "Test Co",
            "ticker": ticker,
            "sector": "Testing",
            "pais": "Testland",
            "alocacion_pct": alocacion,
            "descuento_fv_pct": 20,
            "portafolio_actualizado": {"posiciones": [], "cash_disponible_pct": 100},
        })
        + "\n```\n"
    )


def test_update_crea_archivo_y_agrega_fila(tmp_path):
    path = tmp_path / "escenarios_consolidados.json"
    results = {
        "El Consejo de los Especialistas": _a8_json(),
        "Portfolio Manager": _a9_json(),
    }
    fila = update_escenarios_consolidados("Test Co", results, path=str(path))

    assert fila is not None
    assert fila["ticker"] == "TST"
    assert fila["rating"] == 7.5
    assert fila["alocacion_pct"] == 5
    assert fila["eu"] == "Full"  # primera vez que aparece esta empresa
    # EV ponderado: 110*0.35 + 160*0.40 + 220*0.25 = 38.5 + 64 + 55 = 157.5
    assert fila["ev_5y"] == 157.5
    assert fila["upside_pct"] == round((157.5 - 100.0) / 100.0 * 100, 1)

    data = load_escenarios(str(path))
    assert len(data["empresas"]) == 1


def test_update_es_upsert_no_duplica_ticker(tmp_path):
    path = tmp_path / "escenarios_consolidados.json"
    results = {"El Consejo de los Especialistas": _a8_json(rating=7.0), "Portfolio Manager": _a9_json()}
    update_escenarios_consolidados("Test Co", results, path=str(path))

    # Refresh con rating apenas distinto -> debe pisar la misma fila, no duplicar
    results2 = {"El Consejo de los Especialistas": _a8_json(rating=7.1), "Portfolio Manager": _a9_json()}
    update_escenarios_consolidados("Test Co", results2, path=str(path))

    data = load_escenarios(str(path))
    assert len(data["empresas"]) == 1
    assert data["empresas"][0]["rating"] == 7.1


def test_eu_confirma_ajuste_deterioro(tmp_path):
    path = tmp_path / "escenarios_consolidados.json"
    base = {"Portfolio Manager": _a9_json()}

    base["El Consejo de los Especialistas"] = _a8_json(rating=7.0)
    update_escenarios_consolidados("Test Co", base, path=str(path))

    # Variación chica (<0.3) -> Confirma
    base["El Consejo de los Especialistas"] = _a8_json(rating=7.2)
    fila = update_escenarios_consolidados("Test Co", base, path=str(path))
    assert fila["eu"] == "Confirma"

    # Sube fuerte -> Ajuste
    base["El Consejo de los Especialistas"] = _a8_json(rating=8.5)
    fila = update_escenarios_consolidados("Test Co", base, path=str(path))
    assert fila["eu"] == "Ajuste"

    # Baja fuerte -> Deterioro
    base["El Consejo de los Especialistas"] = _a8_json(rating=6.0)
    fila = update_escenarios_consolidados("Test Co", base, path=str(path))
    assert fila["eu"] == "Deterioro"


def test_pabrai_alert_verde_amarillo_rojo(tmp_path):
    path = tmp_path / "escenarios_consolidados.json"
    results = {"El Consejo de los Especialistas": _a8_json(), "Portfolio Manager": _a9_json(alocacion=5)}

    # Alocación (5%) dentro del rango sugerido -> verde
    fila = update_escenarios_consolidados(
        "Test Co", results, pabrai_resumen={"sizing_recomendado": "3-5%", "red_flags_criticas": 2, "showstoppers": []},
        path=str(path),
    )
    assert fila["pabrai"]["alerta"] == "verde"

    # Alocación (5%) 2pp por encima del techo (2%) -> amarillo
    results["Portfolio Manager"] = _a9_json(alocacion=5)
    fila = update_escenarios_consolidados(
        "Test Co", results, pabrai_resumen={"sizing_recomendado": "≤2% o pasar", "red_flags_criticas": 6, "showstoppers": []},
        path=str(path),
    )
    assert fila["pabrai"]["alerta"] == "amarillo"

    # Alocación (9%) muy por encima del techo (2%) -> rojo
    results["Portfolio Manager"] = _a9_json(alocacion=9)
    fila = update_escenarios_consolidados(
        "Test Co", results, pabrai_resumen={"sizing_recomendado": "≤2% o pasar", "red_flags_criticas": 9, "showstoppers": []},
        path=str(path),
    )
    assert fila["pabrai"]["alerta"] == "rojo"


def test_sin_bloque_json_de_escenarios_no_rompe(tmp_path):
    path = tmp_path / "escenarios_consolidados.json"
    results = {"El Consejo de los Especialistas": "tesis sin bloque json todavía", "Portfolio Manager": _a9_json()}
    fila = update_escenarios_consolidados("Test Co", results, path=str(path))
    assert fila is None
    # No debe crear el archivo si no hay nada que guardar
    assert not path.exists()
