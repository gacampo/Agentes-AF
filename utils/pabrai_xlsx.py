"""Lectura/escritura del checklist Pabrai (.xlsx) — código puro, sin LLM.

El Agente 11 decide QUÉ poner en cada celda (veredicto/severidad/notas); este
módulo decide DÓNDE va cada cosa y hace la aritmética del panel de
evaluación. Mismo principio que utils/validation.py: separar razonamiento
(LLM) de estructura/cálculo (código determinístico).

Estructura del archivo (ver hoja "PLANTILLA (duplicar)"):
- Columna A: número de pregunta (int) o heading de sección (str que empieza
  con "N. ", ej. "1. APALANCAMIENTO / DEUDA...").
- Columna B: texto de la pregunta.
- Columnas C, D, E: VEREDICTO, SEVERIDAD, NOTAS de la corrida FULL inicial.
- Refreshes trimestrales sucesivos agregan bloques de 3 columnas nuevas a la
  derecha (F/G/H, I/J/K, ...), cada uno con su propio header de fecha en la
  fila 6 — así se preserva el historial completo en vez de sobreescribir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

TEMPLATE_SHEET_NAME = "PLANTILLA (duplicar)"
HEADER_ROW = 6  # fila con "#", "PREGUNTA", "VEREDICTO", "SEVERIDAD", "NOTAS"
FIRST_QUESTION_ROW = 7
VEREDICTO_COL_OFFSET = 0  # dentro de cada bloque de 3: 0=VEREDICTO, 1=SEVERIDAD, 2=NOTAS
FIRST_BLOCK_START_COL = 3  # columna C

_SECTION_HEADING_RE = re.compile(r"^\d+\.\s")

# Las primeras 3 secciones del checklist son las "críticas" (Leverage, Moat,
# Management) — se identifican dinámicamente por orden de aparición en el
# template, no por texto hardcodeado, para no romper si el usuario edita
# ligeramente los nombres de sección.
N_CRITICAL_SECTIONS = 3


@dataclass
class Question:
    id: int
    pregunta: str
    seccion: str
    row: int
    is_critical: bool


def load_question_schema(wb: openpyxl.Workbook) -> list[Question]:
    """Lee la hoja PLANTILLA y arma la lista de las 153 preguntas con su fila,
    sección y si esa sección es una de las 3 críticas."""
    ws = wb[TEMPLATE_SHEET_NAME]
    questions: list[Question] = []
    current_section: str | None = None
    section_order: list[str] = []

    for row in range(HEADER_ROW + 1, ws.max_row + 1):
        a_val = ws.cell(row=row, column=1).value
        b_val = ws.cell(row=row, column=2).value
        if a_val is None:
            continue
        if isinstance(a_val, str) and _SECTION_HEADING_RE.match(a_val.strip()):
            current_section = a_val.strip()
            if current_section not in section_order:
                section_order.append(current_section)
            continue
        if isinstance(a_val, int) and current_section is not None:
            questions.append(
                Question(id=a_val, pregunta=b_val or "", seccion=current_section, row=row, is_critical=False)
            )

    critical_names = set(section_order[:N_CRITICAL_SECTIONS])
    for q in questions:
        q.is_critical = q.seccion in critical_names

    return questions


def get_or_create_company_sheet(wb: openpyxl.Workbook, sheet_name: str) -> Worksheet:
    """Retorna la hoja de la empresa si ya existe, o la crea copiando la
    PLANTILLA (preserva formato/estructura de fila)."""
    safe_name = sheet_name[:31]  # límite de Excel para nombres de hoja
    if safe_name in wb.sheetnames:
        return wb[safe_name]
    template = wb[TEMPLATE_SHEET_NAME]
    new_ws = wb.copy_worksheet(template)
    new_ws.title = safe_name
    # Ubicarla antes de la plantilla/guía para que quede agrupada con las
    # demás empresas, no al final.
    wb.move_sheet(safe_name, offset=-(len(wb.sheetnames) - wb.sheetnames.index(TEMPLATE_SHEET_NAME)))
    return new_ws


def _next_free_block_start_col(ws: Worksheet) -> int:
    """Encuentra la columna donde debería arrancar el próximo bloque de 3
    (VEREDICTO/SEVERIDAD/NOTAS) — el primero libre después del último usado."""
    col = FIRST_BLOCK_START_COL
    while ws.cell(row=HEADER_ROW, column=col).value not in (None, ""):
        col += 3
    return col


def write_answers(
    ws: Worksheet,
    questions: list[Question],
    answers: dict[int, dict],
    block_start_col: int,
    header_label: str,
) -> list[int]:
    """Escribe un bloque de respuestas (veredicto/severidad/notas) en las
    columnas [block_start_col, block_start_col+2]. Preguntas sin respuesta en
    `answers` quedan en blanco en este bloque (correcto para refresh lite,
    donde solo se tocan algunas secciones). Retorna los IDs efectivamente
    escritos, para logging/validación."""
    ws.cell(row=HEADER_ROW, column=block_start_col, value=f"VEREDICTO {header_label}")
    ws.cell(row=HEADER_ROW, column=block_start_col + 1, value="SEVERIDAD")
    ws.cell(row=HEADER_ROW, column=block_start_col + 2, value=f"NOTAS {header_label}")

    written: list[int] = []
    for q in questions:
        ans = answers.get(q.id)
        if not ans:
            continue
        ws.cell(row=q.row, column=block_start_col, value=ans.get("veredicto", ""))
        ws.cell(row=q.row, column=block_start_col + 1, value=ans.get("severidad", ""))
        ws.cell(row=q.row, column=block_start_col + 2, value=ans.get("notas", ""))
        written.append(q.id)
    return written


def _last_nonblank_veredicto(ws: Worksheet, row: int, max_block_start_col: int) -> str | None:
    """Recorre los bloques de VEREDICTO de derecha a izquierda y retorna el
    primero no vacío — el estado más actual de esa pregunta, sin importar en
    qué refresh se haya actualizado por última vez."""
    col = max_block_start_col
    while col >= FIRST_BLOCK_START_COL:
        val = ws.cell(row=row, column=col).value
        if val not in (None, ""):
            return str(val)
        col -= 3
    return None


def recompute_panel(ws: Worksheet, questions: list[Question], fecha_label: str) -> dict:
    """Recalcula el panel de evaluación (showstoppers, red flags, sizing)
    tomando SIEMPRE la última respuesta no vacía de cada fila — así el panel
    refleja el estado actual aunque distintas secciones se hayan actualizado
    en distintos refreshes. Es aritmética pura en código, no depende del LLM.

    Retorna un dict con el resumen (también usado para el historial de sizing).
    """
    max_col = _next_free_block_start_col(ws) - 3  # último bloque escrito

    showstoppers: list[int] = []
    red_flags_criticas = 0
    red_flags_secundarias = 0
    sin_responder: list[int] = []

    for q in questions:
        veredicto = _last_nonblank_veredicto(ws, q.row, max_col)
        if veredicto is None or not veredicto.strip():
            sin_responder.append(q.id)
            continue
        if "🛑" in veredicto:
            showstoppers.append(q.id)
        elif "⚠" in veredicto:
            if q.is_critical:
                red_flags_criticas += 1
            else:
                red_flags_secundarias += 1

    if showstoppers:
        sizing = "0% — NO INVERTIR (showstopper en sección crítica)"
    elif red_flags_criticas > 5:
        sizing = "Mucha cautela: 2% máx. o pasar (>5 red flags en secciones críticas)"
    elif 2 <= red_flags_criticas <= 4:
        sizing = "Posición moderada: 3-5% (2-4 red flags en secciones críticas)"
    else:
        sizing = "Posición estándar sugerida: 5% (hasta 7-10% requiere alta convicción — criterio manual)"

    decision = "NO INVERTIR" if showstoppers else ("ESPERAR" if sin_responder else "EVALUAR PARA INVERTIR")

    resumen = {
        "fecha": fecha_label,
        "showstoppers": showstoppers,
        "red_flags_criticas": red_flags_criticas,
        "red_flags_secundarias": red_flags_secundarias,
        "sin_responder": sin_responder,
        "sizing_recomendado": sizing,
        "decision_sugerida": decision,
    }

    ws["C191"] = "SÍ" if showstoppers else "No"
    ws["C192"] = red_flags_criticas
    ws["C193"] = red_flags_secundarias
    ws["C194"] = f"{len(sin_responder)} preguntas" if sin_responder else "No"
    ws["C195"] = sizing
    ws["C196"] = decision

    _append_sizing_history(ws, resumen)
    return resumen


_HISTORY_HEADER = ["Fecha", "Showstoppers", "Red flags críticas", "Red flags secundarias", "Sizing recomendado", "Decisión"]


def _append_sizing_history(ws: Worksheet, resumen: dict) -> None:
    """Agrega una fila a la tabla 'Historial de sizing' (la crea si no existe),
    debajo del panel de evaluación — para ver de un vistazo cómo evolucionó
    la convicción sobre la empresa a lo largo de los refreshes."""
    HISTORY_TITLE_ROW = 198
    HISTORY_HEADER_ROW = 199

    if ws.cell(row=HISTORY_TITLE_ROW, column=1).value != "═══ HISTORIAL DE SIZING ═══":
        ws.cell(row=HISTORY_TITLE_ROW, column=1, value="═══ HISTORIAL DE SIZING ═══")
        for i, label in enumerate(_HISTORY_HEADER):
            ws.cell(row=HISTORY_HEADER_ROW, column=1 + i, value=label)

    next_row = HISTORY_HEADER_ROW + 1
    while any(ws.cell(row=next_row, column=c).value not in (None, "") for c in range(1, 7)):
        next_row += 1

    ws.cell(row=next_row, column=1, value=resumen["fecha"])
    ws.cell(row=next_row, column=2, value="Sí" if resumen["showstoppers"] else "No")
    ws.cell(row=next_row, column=3, value=resumen["red_flags_criticas"])
    ws.cell(row=next_row, column=4, value=resumen["red_flags_secundarias"])
    ws.cell(row=next_row, column=5, value=resumen["sizing_recomendado"])
    ws.cell(row=next_row, column=6, value=resumen["decision_sugerida"])


def apply_full_checklist(
    workbook_path: str,
    sheet_name: str,
    company_header: str,
    summary_line: str,
    answers: dict[int, dict],
    fecha_label: str,
) -> dict:
    """Punto de entrada para una corrida FULL: crea (o reusa) la hoja de la
    empresa y escribe las 153 respuestas en el primer bloque de columnas."""
    wb = openpyxl.load_workbook(workbook_path)
    questions = load_question_schema(wb)
    ws = get_or_create_company_sheet(wb, sheet_name)
    ws["A1"] = company_header
    ws["A2"] = summary_line
    written = write_answers(ws, questions, answers, FIRST_BLOCK_START_COL, fecha_label)
    resumen = recompute_panel(ws, questions, fecha_label)
    wb.save(workbook_path)
    resumen["preguntas_escritas"] = len(written)
    resumen["preguntas_totales"] = len(questions)
    return resumen


def apply_lite_refresh(
    workbook_path: str,
    sheet_name: str,
    answers: dict[int, dict],
    fecha_label: str,
) -> dict:
    """Punto de entrada para un refresh: agrega un bloque de 3 columnas nuevo
    con solo las preguntas tocadas este trimestre (el resto queda en blanco
    en ese bloque — el panel las toma de la última columna donde sí tengan
    respuesta)."""
    wb = openpyxl.load_workbook(workbook_path)
    if sheet_name[:31] not in wb.sheetnames:
        raise ValueError(
            f"No existe la hoja '{sheet_name}' — corré primero el checklist FULL para esta empresa."
        )
    questions = load_question_schema(wb)
    ws = wb[sheet_name[:31]]
    block_start_col = _next_free_block_start_col(ws)
    written = write_answers(ws, questions, answers, block_start_col, fecha_label)
    resumen = recompute_panel(ws, questions, fecha_label)
    wb.save(workbook_path)
    resumen["preguntas_escritas"] = len(written)
    resumen["preguntas_totales"] = len(questions)
    return resumen
