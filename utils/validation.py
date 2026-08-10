"""Validación determinística de outputs numéricos de los agentes.

Los agentes que emiten datos cuantitativos (tablas de métricas, escenarios de
valoración, alocación de portafolio) deben cerrar esa sección con un bloque
```json fenced con los valores estructurados. Este módulo extrae ese bloque
y corre chequeos de consistencia en código Python — no delega la aritmética
al LLM. La idea es la misma en los tres casos: el LLM decide QUÉ dato usar,
el código verifica que el dato SUME/CIERRE bien.

Todas las funciones son no-destructivas: nunca modifican los números, solo
señalan inconsistencias para que una persona las revise.
"""

from __future__ import annotations

import json
import re


def extract_json_block(text: str) -> dict | list | None:
    """Extrae el último bloque ```json ... ``` del texto y lo parsea.

    Retorna None si no hay bloque o si no es JSON válido (en vez de tirar
    excepción) — el llamador decide qué hacer con la ausencia de datos.
    """
    matches = re.findall(r"```json\s*(.*?)```", text, re.DOTALL)
    if not matches:
        return None
    raw = matches[-1].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def annotate_with_warnings(text: str, issues: list[str], title: str) -> str:
    """Agrega un bloque de advertencia visible al final del texto si hay issues.

    Si issues está vacío, retorna el texto sin cambios.
    """
    if not issues:
        return text
    lines = [f"\n\n---\n\n> ⚠️ **{title}** — revisar antes de confiar en estos números:"]
    for issue in issues:
        lines.append(f"> - {issue}")
    return text + "\n".join(lines) + "\n"


# ═══════════════════════ Agente 7: tabla de métricas (Fase B) ═══════════════════════

_PCT_RANGE = (-100.0, 500.0)
_X_RANGE = (-5.0, 100.0)


def validate_metrics_json(data) -> list[str]:
    """Valida el bloque JSON de métricas del Organizador Principal (Agente 7).

    Chequea: estructura completa, valores numéricos plausibles, y que el
    flag 'cumple' sea consistente con valor/umbral/dirección declarados.
    """
    if not isinstance(data, dict) or not isinstance(data.get("metricas"), list):
        return ["El bloque JSON no tiene la forma esperada: {\"metricas\": [...]}."]

    metricas = data["metricas"]
    if not metricas:
        return ["El bloque JSON de métricas está vacío."]

    required = {"metrica", "valor_actual", "unidad", "direccion", "umbral", "cumple"}
    issues: list[str] = []

    for i, m in enumerate(metricas):
        if not isinstance(m, dict):
            issues.append(f"Métrica #{i}: no es un objeto JSON válido.")
            continue
        missing = required - set(m.keys())
        label = m.get("metrica", f"#{i}")
        if missing:
            issues.append(f"{label}: faltan campos obligatorios {sorted(missing)}.")
            continue

        valor = m["valor_actual"]
        unidad = m["unidad"]
        direccion = m["direccion"]
        umbral = m["umbral"]
        cumple = m["cumple"]

        if not isinstance(valor, (int, float)):
            issues.append(f"{label}: valor_actual no es numérico ({valor!r}).")
            continue

        if unidad == "%" and not (_PCT_RANGE[0] <= valor <= _PCT_RANGE[1]):
            issues.append(f"{label}: {valor}% está fuera de un rango plausible.")
        elif unidad == "x" and not (_X_RANGE[0] <= valor <= _X_RANGE[1]):
            issues.append(f"{label}: {valor}x está fuera de un rango plausible.")

        if direccion in ("mayor_mejor", "menor_mejor") and umbral is not None and isinstance(cumple, bool):
            if not isinstance(umbral, (int, float)):
                issues.append(f"{label}: umbral no es numérico ({umbral!r}).")
                continue
            esperado = (valor >= umbral) if direccion == "mayor_mejor" else (valor <= umbral)
            if esperado != cumple:
                issues.append(
                    f"{label}: valor={valor}{unidad}, umbral={umbral}{unidad}, dirección={direccion} "
                    f"→ 'cumple' debería ser {esperado}, pero el agente puso {cumple}."
                )
        elif direccion not in ("mayor_mejor", "menor_mejor", "informativo"):
            issues.append(f"{label}: dirección '{direccion}' no reconocida.")

    return issues


# ═══════════════════════ Agente 8: escenarios/TIR y rating ═══════════════════════

_RATING_WEIGHTS = (0.6, 0.4)  # (calidad_negocio, atractivo_valoracion)


def validate_scenarios_json(data, tir_tolerance_pp: float = 5.0, rating_tolerance: float = 0.15) -> list[str]:
    """Valida el bloque JSON de escenarios/TIR y rating del Agente 8 (Council).

    No recalcula el DCF (eso requeriría reproducir todos los supuestos del
    modelo) — chequea que la TIR declarada sea *consistente* con valor
    intrínseco/precio implícitos (proxy de "cierra la aritmética básica"), y
    que el rating compuesto sea el promedio ponderado 60/40 declarado.

    IMPORTANTE: usa un valor intrínseco DISTINTO por horizonte
    (valor_intrinseco_5y para la TIR a 5 años, valor_intrinseco_10y para la
    TIR a 10 años) — muchas tesis proyectan un precio objetivo distinto para
    cada horizonte (crecimiento compuesto), así que comparar la TIR a 10 años
    contra el valor del año 5 da un falso positivo sistemático.
    """
    if not isinstance(data, dict):
        return ["El bloque JSON no es un objeto válido."]

    issues: list[str] = []

    escenarios = data.get("escenarios")
    if not isinstance(escenarios, list) or not escenarios:
        issues.append("Falta 'escenarios' (lista) o está vacía en el bloque JSON.")
    else:
        for esc in escenarios:
            nombre = esc.get("nombre", "?") if isinstance(esc, dict) else "?"
            if not isinstance(esc, dict):
                issues.append(f"Escenario '{nombre}': no es un objeto JSON válido.")
                continue
            try:
                vi_5y = float(esc["valor_intrinseco_5y"])
                vi_10y = float(esc["valor_intrinseco_10y"])
                precio = float(esc["precio_actual"])
                tir5 = float(esc["tir_5y_pct"])
                tir10 = float(esc["tir_10y_pct"])
            except (KeyError, TypeError, ValueError) as e:
                issues.append(f"Escenario '{nombre}': faltan campos numéricos o no son válidos ({e}).")
                continue

            if vi_5y <= 0 or vi_10y <= 0 or precio <= 0:
                issues.append(f"Escenario '{nombre}': valor_intrinseco_5y, valor_intrinseco_10y y precio_actual deben ser > 0.")
                continue

            for years, vi, tir_declarada in ((5, vi_5y, tir5), (10, vi_10y, tir10)):
                ratio = vi / precio
                tir_implicita_pct = (ratio ** (1 / years) - 1) * 100
                if abs(tir_implicita_pct - tir_declarada) > tir_tolerance_pp:
                    issues.append(
                        f"Escenario '{nombre}': TIR {years} años declarada ({tir_declarada:.1f}%) se aleja "
                        f">±{tir_tolerance_pp:.0f}pp de la implícita por valor_intrinseco_{years}y/precio_actual "
                        f"({tir_implicita_pct:.1f}%) sin dividendos/recompras — si el negocio paga dividendos "
                        "materiales o hace recompras significativas esto puede ser normal (la TIR total incluye "
                        "ese efecto), pero conviene revisarlo."
                    )

    rating = data.get("rating")
    if not isinstance(rating, dict):
        issues.append("Falta el objeto 'rating' en el bloque JSON.")
    else:
        try:
            calidad = float(rating["calidad_negocio"])
            valoracion = float(rating["atractivo_valoracion"])
            compuesto = float(rating["rating_compuesto"])
        except (KeyError, TypeError, ValueError) as e:
            issues.append(f"'rating': faltan campos numéricos o no son válidos ({e}).")
        else:
            for etiqueta, val in (("calidad_negocio", calidad), ("atractivo_valoracion", valoracion), ("rating_compuesto", compuesto)):
                if not (0.0 <= val <= 10.0):
                    issues.append(f"rating.{etiqueta}={val} está fuera del rango 0-10.")
            esperado = _RATING_WEIGHTS[0] * calidad + _RATING_WEIGHTS[1] * valoracion
            if abs(esperado - compuesto) > rating_tolerance:
                issues.append(
                    f"rating_compuesto declarado ({compuesto:.2f}) no coincide con el promedio ponderado "
                    f"60/40 esperado ({esperado:.2f}) a partir de calidad_negocio={calidad:.1f} y "
                    f"atractivo_valoracion={valoracion:.1f}."
                )

    return issues


# ═══════════════════════ Agente 9: alocación de portafolio (BLOQUEANTE) ═══════════════════════

class PortfolioValidationError(Exception):
    """Se levanta cuando la alocación propuesta rompe las reglas de concentración
    o no cierra aritméticamente. A diferencia de los validadores de 7 y 8 (que
    solo anotan advertencias), esta validación es bloqueante: si falla, NO se
    persiste el portafolio actualizado en disco."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("; ".join(issues))


def validate_portfolio_json(data, reglas: dict, tolerance_pct: float = 0.5) -> list[str]:
    """Valida el bloque JSON de decisión de alocación del Agente 9.

    Chequea: estructura, que la nueva posición respete los límites de la
    empresa, y que el portafolio actualizado completo (todas las posiciones +
    cash) cierre en ~100% y respete los límites de concentración por
    sector/país. Retorna la lista de issues (vacía = todo OK).
    """
    if not isinstance(data, dict):
        return ["El bloque JSON no es un objeto válido."]

    issues: list[str] = []

    decision = data.get("decision")
    if decision not in ("INGRESA", "NO INGRESA"):
        issues.append(f"'decision' debe ser 'INGRESA' o 'NO INGRESA', recibido: {decision!r}.")

    if decision == "INGRESA":
        alocacion = data.get("alocacion_pct")
        if not isinstance(alocacion, (int, float)):
            issues.append("'alocacion_pct' falta o no es numérico pese a decision=INGRESA.")
        else:
            max_empresa = reglas.get("max_por_empresa_pct", 10.0)
            min_pos = reglas.get("min_posicion_pct", 1.0)
            if alocacion > max_empresa:
                issues.append(
                    f"alocacion_pct={alocacion}% supera el máximo por empresa ({max_empresa}%)."
                )
            if alocacion < min_pos:
                issues.append(
                    f"alocacion_pct={alocacion}% es menor al mínimo por posición ({min_pos}%): "
                    "si la convicción no llega al mínimo, no debería ingresar."
                )

    portafolio = data.get("portafolio_actualizado")
    if not isinstance(portafolio, dict) or not isinstance(portafolio.get("posiciones"), list):
        issues.append("Falta 'portafolio_actualizado.posiciones' (lista) en el bloque JSON.")
        return issues  # sin esto no se puede validar el resto

    posiciones = portafolio["posiciones"]
    cash = portafolio.get("cash_disponible_pct")
    if not isinstance(cash, (int, float)):
        issues.append("'portafolio_actualizado.cash_disponible_pct' falta o no es numérico.")
        cash = 0.0

    max_empresa = reglas.get("max_por_empresa_pct", 10.0)
    max_sector = reglas.get("max_por_sector_pct", 25.0)
    max_pais = reglas.get("max_por_pais_pct", 25.0)

    total_posiciones = 0.0
    sector_totals: dict[str, float] = {}
    pais_totals: dict[str, float] = {}

    for i, pos in enumerate(posiciones):
        if not isinstance(pos, dict):
            issues.append(f"Posición #{i}: no es un objeto JSON válido.")
            continue
        try:
            pct = float(pos["alocacion_pct"])
        except (KeyError, TypeError, ValueError):
            issues.append(f"Posición #{i} ({pos.get('empresa', '?')}): alocacion_pct falta o no es numérico.")
            continue
        empresa = pos.get("empresa", f"#{i}")
        sector = pos.get("sector", "Sin sector")
        pais = pos.get("pais", "Sin país")

        if pct > max_empresa + tolerance_pct:
            issues.append(f"{empresa}: alocación {pct}% supera el máximo por empresa ({max_empresa}%).")

        total_posiciones += pct
        sector_totals[sector] = sector_totals.get(sector, 0.0) + pct
        pais_totals[pais] = pais_totals.get(pais, 0.0) + pct

    total = total_posiciones + cash
    if abs(total - 100.0) > tolerance_pct:
        issues.append(
            f"El portafolio no cierra en 100%: posiciones={total_posiciones:.1f}% + "
            f"cash={cash:.1f}% = {total:.1f}%."
        )

    for sector, pct in sector_totals.items():
        if pct > max_sector + tolerance_pct:
            issues.append(f"Sector '{sector}': concentración {pct:.1f}% supera el máximo ({max_sector}%).")
    for pais, pct in pais_totals.items():
        if pct > max_pais + tolerance_pct:
            issues.append(f"País '{pais}': concentración {pct:.1f}% supera el máximo ({max_pais}%).")

    return issues


# ═══════════════════════ Agente 11: checklist Pabrai ═══════════════════════

VALID_VEREDICTOS = {"OK", "⚠️ Red Flag", "🛑 Showstopper", "N/A"}


def validate_pabrai_answers(data, expected_ids: set[int]) -> list[str]:
    """Valida el bloque JSON de respuestas del Agente 11 (Pabrai Checklist).

    No bloqueante (como el Agente 7): anota problemas de estructura pero no
    impide escribir lo que sí vino bien formado. Chequea: forma del JSON,
    que los IDs respondidos sean un subconjunto/igual a los esperados, y que
    cada respuesta tenga veredicto válido y notas no vacías.
    """
    if not isinstance(data, dict) or not isinstance(data.get("respuestas"), list):
        return ["El bloque JSON no tiene la forma esperada: {\"respuestas\": [...]}."]

    respuestas = data["respuestas"]
    if not respuestas:
        return ["El bloque JSON de respuestas está vacío."]

    issues: list[str] = []
    seen_ids: set[int] = set()

    for i, r in enumerate(respuestas):
        if not isinstance(r, dict):
            issues.append(f"Respuesta #{i}: no es un objeto JSON válido.")
            continue
        rid = r.get("id")
        if not isinstance(rid, int):
            issues.append(f"Respuesta #{i}: 'id' falta o no es entero ({rid!r}).")
            continue
        seen_ids.add(rid)
        veredicto = r.get("veredicto")
        if veredicto not in VALID_VEREDICTOS:
            issues.append(f"Pregunta {rid}: veredicto '{veredicto}' no es uno de {sorted(VALID_VEREDICTOS)}.")
        notas = r.get("notas")
        if not isinstance(notas, str) or not notas.strip():
            issues.append(f"Pregunta {rid}: falta 'notas' (evidencia/justificación).")

    faltantes = expected_ids - seen_ids
    if faltantes:
        issues.append(f"Faltan {len(faltantes)} pregunta(s) sin responder: IDs {sorted(faltantes)}.")

    inesperadas = seen_ids - expected_ids
    if inesperadas:
        issues.append(f"Se respondieron {len(inesperadas)} ID(s) no esperados para esta corrida: {sorted(inesperadas)}.")

    return issues
