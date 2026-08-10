"""Tests de utils/history_db.py."""

from __future__ import annotations

from utils import history_db


def test_record_and_get_latest_per_company(tmp_path):
    db = str(tmp_path / "historial.db")

    history_db.record_run(
        "Empresa A", "full", db_path=db, ticker="EMPA", sector="Tech", pais="USA",
        fecha="01-Ene-2026", precio_referencia=100.0, calidad_negocio=8.0,
        atractivo_valoracion=6.0, rating_compuesto=7.2, decision_portafolio="INGRESA",
        alocacion_pct=5.0,
    )
    history_db.record_run(
        "Empresa A", "lite", db_path=db, ticker="EMPA", sector="Tech", pais="USA",
        fecha="10-Ago-2026", precio_referencia=110.0, calidad_negocio=8.0,
        atractivo_valoracion=5.5, rating_compuesto=6.9, decision_portafolio="INGRESA",
        alocacion_pct=5.0,
    )
    history_db.record_run(
        "Empresa B", "full", db_path=db, ticker="EMPB", sector="Salud", pais="Argentina",
        fecha="05-Feb-2026", precio_referencia=50.0, decision_portafolio="NO INGRESA",
    )

    latest = history_db.get_latest_per_company(db_path=db)
    assert len(latest) == 2
    by_company = {r["company"]: r for r in latest}
    assert by_company["Empresa A"]["precio_referencia"] == 110.0
    assert by_company["Empresa A"]["mode"] == "lite"
    assert by_company["Empresa B"]["decision_portafolio"] == "NO INGRESA"


def test_get_history_orden_cronologico(tmp_path):
    db = str(tmp_path / "historial.db")
    history_db.record_run("Empresa A", "full", db_path=db, rating_compuesto=7.0)
    history_db.record_run("Empresa A", "lite", db_path=db, rating_compuesto=7.5)
    history_db.record_run("Empresa A", "lite", db_path=db, rating_compuesto=6.8)

    hist = history_db.get_history("Empresa A", db_path=db)
    assert [r["mode"] for r in hist] == ["full", "lite", "lite"]
    assert [r["rating_compuesto"] for r in hist] == [7.0, 7.5, 6.8]


def test_campos_opcionales_faltantes_no_rompen(tmp_path):
    """record_run no debe fallar si faltan campos opcionales (ej. corrida
    sin ticker o sin rating parseable)."""
    db = str(tmp_path / "historial.db")
    history_db.record_run("Empresa Incompleta", "full", db_path=db)
    latest = history_db.get_latest_per_company(db_path=db)
    assert len(latest) == 1
    assert latest[0]["ticker"] is None
    assert latest[0]["rating_compuesto"] is None


def test_empresas_distintas_no_se_mezclan(tmp_path):
    db = str(tmp_path / "historial.db")
    history_db.record_run("A", "full", db_path=db, precio_referencia=10.0)
    history_db.record_run("B", "full", db_path=db, precio_referencia=20.0)
    history_db.record_run("A", "lite", db_path=db, precio_referencia=15.0)

    assert len(history_db.get_history("A", db_path=db)) == 2
    assert len(history_db.get_history("B", db_path=db)) == 1
