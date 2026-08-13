"""Mantiene reportes/escenarios_consolidados.json — la tabla maestra con el
resumen de escenarios (Conservador/Base/Optimista), rating, alocación y la
alerta del checklist Pabrai de cada empresa ya corrida, para tener de un
vistazo cómo está parada cada tesis y cómo evolucionó en el tiempo.

Se llama automáticamente al final de run_analysis() (main.py), igual que
_record_history() — es un complemento de solo-lectura de los JSON ya
validados por los Agentes 8/9/11, nunca debe romper la corrida principal si
algo no se puede parsear.

Formato del archivo (ver también el PDF que arma visualize_escenarios.py):
{
  "metodologia": {...},
  "empresas": [
    {"ticker": ..., "empresa": ..., "moneda": ..., "precio": ..., "alocacion_pct": ...,
     "rating": ..., "fecha_refresh": ..., "escenarios": {...}, "ev_5y": ..., "upside_pct": ...,
     "pabrai": {...} | null, "eu": "Full"|"Confirma"|"Ajuste"|"Deterioro", "historial": [...]}
  ]
}
"""

from __future__ import annotations

import json
from pathlib import Path

ESCENARIOS_FILE = "reportes/escenarios_consolidados.json"

# Probabilidades default para el cálculo de EV ponderado, colapsando el
# histórico esquema de 5 escenarios (Bear/Conservador/Base/Optimista/Bull)
# a los 3 que produce el Agente 8 actual: Bear→Conservador, Bull→Optimista.
PROB_DEFAULT = {"conservador": 35, "base": 40, "optimista": 25}

# Umbral de variación de rating_compuesto para decidir el status EU en un
# refresh sobre una empresa que ya estaba en la tabla.
_EU_CONFIRMA_TOLERANCIA = 0.3  # puntos de rating


def _empty_file() -> dict:
    return {
        "metodologia": {
            "horizonte": "5 años (valor intrínseco y TIR anualizada a 5y de cada escenario del Agente 8)",
            "probabilidades_default": PROB_DEFAULT,
            "pabrai_alert": (
                "Compara la alocación decidida por el Agente 9 contra el 'sizing_recomendado' "
                "mecánico del checklist Pabrai (si se corrió). verde = alineado. amarillo = "
                "hasta 3pp por encima del techo sugerido. rojo = más de 3pp por encima, o el "
                "checklist sugiere pasar/posición mínima."
            ),
        },
        "empresas": [],
    }


def load_escenarios(path: str = ESCENARIOS_FILE) -> dict:
    p = Path(path)
    if not p.exists():
        return _empty_file()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_file()


def save_escenarios(data: dict, path: str = ESCENARIOS_FILE) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _weighted_ev(escenarios: dict, horizon_key: str = "fv_5y") -> float | None:
    try:
        return sum(
            escenarios[k][horizon_key] * escenarios[k]["prob_pct"] / 100
            for k in ("conservador", "base", "optimista")
        )
    except (KeyError, TypeError):
        return None


def _pabrai_alert_level(alocacion_pct: float, sizing_recomendado: str) -> str:
    """Deriva un semáforo simple comparando la alocación real contra el
    techo numérico que se puede extraer de 'sizing_recomendado' (texto libre
    tipo '3-5%', '≤2% o pasar', 'Full 10%'). Si no se puede parsear un
    número, devuelve 'amarillo' (no se pudo verificar, mejor no asumir
    alineación silenciosamente)."""
    import re

    numeros = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", sizing_recomendado or "")]
    if not numeros:
        return "amarillo"
    techo = max(numeros)
    if alocacion_pct <= techo:
        return "verde"
    if alocacion_pct <= techo + 3:
        return "amarillo"
    return "rojo"


def _decide_eu(previous: dict | None, nuevo_rating: float | None) -> str:
    if previous is None:
        return "Full"
    prev_rating = previous.get("rating")
    if prev_rating is None or nuevo_rating is None:
        return "Ajuste"
    delta = nuevo_rating - prev_rating
    if abs(delta) <= _EU_CONFIRMA_TOLERANCIA:
        return "Confirma"
    return "Deterioro" if delta < 0 else "Ajuste"


def update_escenarios_consolidados(
    company: str,
    results: dict[str, str],
    pabrai_resumen: dict | None = None,
    path: str = ESCENARIOS_FILE,
) -> dict | None:
    """Upsert de la fila de `company` en escenarios_consolidados.json a partir
    de los bloques JSON YA validados de los Agentes 8 (escenarios+rating) y 9
    (alocación+ticker+sector+país). No vuelve a validar nada — si esos JSON
    no están o no parsean, no rompe la corrida, solo se salta el registro.

    Devuelve la fila insertada/actualizada, o None si no se pudo armar
    (ej. porque la tesis no llegó a tener un bloque JSON de escenarios
    válido — típicamente porque la corrida se cortó antes del Agente 8)."""
    from utils.validation import extract_json_block  # import local: evita ciclo con main.py

    a8 = extract_json_block(results.get("El Consejo de los Especialistas", "")) or {}
    a9 = extract_json_block(results.get("Portfolio Manager", "")) or {}
    if not isinstance(a8, dict) or "escenarios" not in a8 or "rating" not in a8:
        return None

    escenarios_raw = {e["nombre"]: e for e in a8["escenarios"] if e.get("nombre") in ("conservador", "base", "optimista")}
    if len(escenarios_raw) != 3:
        return None
    rating = a8["rating"]

    escenarios = {}
    for nombre, e in escenarios_raw.items():
        escenarios[nombre] = {
            "fv_5y": e.get("valor_intrinseco_5y"),
            "tir_5y_pct": e.get("tir_5y_pct"),
            "prob_pct": PROB_DEFAULT.get(nombre),
        }

    precio = rating.get("precio_referencia")
    ev_5y = _weighted_ev(escenarios)
    upside_pct = round((ev_5y - precio) / precio * 100, 1) if (ev_5y is not None and precio) else None

    pabrai_block = None
    if pabrai_resumen:
        sizing = pabrai_resumen.get("sizing_recomendado", "")
        alocacion = a9.get("alocacion_pct") if isinstance(a9, dict) else None
        pabrai_block = {
            "sizing_sugerido": sizing,
            "red_flags_criticas": pabrai_resumen.get("red_flags_criticas"),
            "showstoppers": len(pabrai_resumen.get("showstoppers") or []),
            "alocacion_actual": alocacion,
            "alerta": _pabrai_alert_level(alocacion, sizing) if alocacion is not None else "amarillo",
        }

    data = load_escenarios(path)
    empresas = data.setdefault("empresas", [])
    ticker = (a9.get("ticker") if isinstance(a9, dict) else None) or company
    existing_idx = next((i for i, e in enumerate(empresas) if e.get("ticker") == ticker), None)
    previous = empresas[existing_idx] if existing_idx is not None else None

    fila = {
        "ticker": ticker,
        "empresa": company,
        "moneda": None,  # se completa a mano si hace falta (el bloque JSON no trae moneda explícita)
        "precio": precio,
        "alocacion_pct": a9.get("alocacion_pct") if isinstance(a9, dict) else None,
        "rating": rating.get("rating_compuesto"),
        "fecha_refresh": rating.get("fecha_rating"),
        "escenarios": escenarios,
        "ev_5y": round(ev_5y, 1) if ev_5y is not None else None,
        "upside_pct": upside_pct,
        "pabrai": pabrai_block if pabrai_block is not None else (previous.get("pabrai") if previous else None),
        "eu": _decide_eu(previous, rating.get("rating_compuesto")),
    }
    if existing_idx is not None:
        empresas[existing_idx] = fila
    else:
        empresas.append(fila)

    save_escenarios(data, path)
    return fila
