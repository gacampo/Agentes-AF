"""Base de historial de corridas (SQLite) — código puro, sin LLM.

Cada vez que main.py termina una corrida (full o lite), graba una fila acá
con el estado resultante: rating, precio de referencia, decisión de
portafolio. Los archivos .md siguen siendo la fuente de verdad legible; esta
base es solo para consultas rápidas ("¿cómo evolucionó el rating de X en el
tiempo?") y es lo que el Delta Detector usa para saber cuál fue el último
precio/fecha registrados por empresa, sin tener que parsear markdown.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = "reportes/historial.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    ticker TEXT,
    sector TEXT,
    pais TEXT,
    mode TEXT NOT NULL,
    fecha TEXT,
    precio_referencia REAL,
    calidad_negocio REAL,
    atractivo_valoracion REAL,
    rating_compuesto REAL,
    decision_portafolio TEXT,
    alocacion_pct REAL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_company ON runs(company);
"""


def _connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def record_run(
    company: str,
    mode: str,
    db_path: str = DEFAULT_DB_PATH,
    ticker: str | None = None,
    sector: str | None = None,
    pais: str | None = None,
    fecha: str | None = None,
    precio_referencia: float | None = None,
    calidad_negocio: float | None = None,
    atractivo_valoracion: float | None = None,
    rating_compuesto: float | None = None,
    decision_portafolio: str | None = None,
    alocacion_pct: float | None = None,
) -> None:
    """Graba una fila de historial para esta corrida. No lanza excepción si
    faltan campos opcionales (ej. una corrida sin --pabrai-xlsx o sin rating
    parseable) — graba lo que hay, con NULL en lo que falte."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO runs
               (company, ticker, sector, pais, mode, fecha, precio_referencia,
                calidad_negocio, atractivo_valoracion, rating_compuesto,
                decision_portafolio, alocacion_pct, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                company, ticker, sector, pais, mode, fecha, precio_referencia,
                calidad_negocio, atractivo_valoracion, rating_compuesto,
                decision_portafolio, alocacion_pct,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_per_company(db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    """Retorna la fila más reciente (por created_at) de cada empresa distinta."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """SELECT r.* FROM runs r
               INNER JOIN (
                   SELECT company, MAX(created_at) AS max_created
                   FROM runs GROUP BY company
               ) latest
               ON r.company = latest.company AND r.created_at = latest.max_created
               ORDER BY r.company"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_history(company: str, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    """Retorna todas las corridas de una empresa, ordenadas de más vieja a más nueva."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM runs WHERE company = ? ORDER BY created_at ASC", (company,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
