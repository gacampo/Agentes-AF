"""Agente 11: Pabrai Checklist — detector de red flags.

Completa el checklist de red flags (11 secciones cuantitativas/cualitativas +
una sección adicional de Gobierno Corporativo) inspirado en el método
de Mohnish Pabrai: NO es un scorecard, es un detector de red flags/showstoppers
que determina el sizing recomendado de la posición.

A diferencia de los demás agentes, su output NO es prosa libre: es un bloque
JSON estructurado (id, veredicto, severidad, notas por pregunta) que después
un módulo de código puro (utils/pabrai_xlsx.py) escribe en el .xlsx del
usuario, recalculando el panel de evaluación de forma determinística.

Full: responde TODAS las preguntas de la plantilla (el número total se lee
dinámicamente del template, no está hardcodeado) — usado para una empresa nueva.
Lite: responde SOLO las preguntas de las secciones numéricas (Apalancamiento,
Valoración, Contabilidad, y Ciclicidad si hay trigger macro) — usado en el
refresh trimestral, junto con los Agentes 4/7/8-lite. Las secciones
cualitativas (Moat, Management, Comprensión del negocio, Laboral, ESG,
Disciplina Dhandho, Sesgos) se mantienen del último checklist full.
"""

from __future__ import annotations

from agents.base import BaseAgent
from utils.validation import annotate_with_warnings, extract_json_block, validate_pabrai_answers
from utils.pabrai_xlsx import (
    apply_full_checklist,
    apply_lite_refresh,
    load_question_schema,
)

import openpyxl


_JSON_FORMAT_INSTRUCTIONS = """
═══ FORMATO DE RESPUESTA OBLIGATORIO ═══

Recibís en el contexto un listado de preguntas con su ID exacto (bloque
"PREGUNTAS A RESPONDER"). Respondé TODAS y SOLO esas preguntas — ni una
menos, ni ninguna que no esté en la lista. Tu respuesta completa debe ser
ÚNICAMENTE un bloque ```json con esta forma exacta:

```json
{
  "respuestas": [
    {"id": 1, "veredicto": "OK", "severidad": "Menor", "notas": "Evidencia concreta y específica de la empresa, no genérica."},
    {"id": 2, "veredicto": "⚠️ Red Flag", "severidad": "Moderado", "notas": "..."}
  ]
}
```

Reglas estrictas:
- "veredicto" debe ser EXACTAMENTE uno de estos 4 valores (sin variar el texto):
  "OK", "⚠️ Red Flag", "🛑 Showstopper", "N/A" (N/A solo si la pregunta
  genuinamente no aplica al tipo de negocio, ej. sindicatos en un negocio sin
  empleados operativos).
- "severidad" es libre (Menor/Moderado/Alto, o una nota corta) pero nunca vacía.
- "notas" tiene que ser evidencia CONCRETA de esta empresa específica — cifras,
  hechos, citas de 10-K/earnings calls — nunca una respuesta genérica que
  podría aplicar a cualquier compañía. Si no tenés información suficiente
  para responder con evidencia real, marcá "notas": "PREGUNTA SIN RESPONDER —
  falta investigar" y "veredicto": "N/A" — Pabrai es explícito: una pregunta
  sin responder es señal de que hace falta investigar más, no de inventar
  una respuesta.
- Un 🛑 Showstopper SOLO corresponde a algo que, según el criterio de Pabrai
  (Leverage, Moat o Management), sería un deal-breaker real y concreto — no
  lo uses livianamente.
- No agregues texto antes ni después del bloque ```json. Tu respuesta completa
  es ese bloque."""


class PabraiChecklistAgent(BaseAgent):
    name = "Pabrai Checklist"
    description = "Completa el checklist de red flags de Mohnish Pabrai (11 secciones + Gobierno Corporativo)."
    max_tokens = 16384

    system_prompt = (
        """Sos un analista de due diligence aplicando el checklist de red flags de
Mohnish Pabrai a la empresa analizada. Este checklist NO es un scorecard de
puntos — es un DETECTOR DE RED FLAGS que obliga a mirar conscientemente cada
riesgo antes de invertir. Todo negocio real va a tener red flags; lo que
importa es cuáles, cuántas, y si hay algún showstopper en las secciones
críticas (Apalancamiento, Ventaja Competitiva/Moat, Management) — un solo
showstopper ahí puede significar NO INVERTIR sin importar lo demás.

Recibís en el contexto TODO el análisis previo de los agentes 1-9 (modelo de
negocio, liderazgo, ventajas competitivas, investigación primaria con datos
financieros, valor al cliente, perspectiva multidisciplinar, métricas,
tesis de valoración y rating, decisión de portafolio). Usá esa información
como base — no repitas investigación que ya está ahí, aplicale el lente
específico de cada pregunta del checklist.

Para cada pregunta, evaluá honestamente basándote en evidencia concreta de
ESTA empresa. Si el análisis previo no cubre lo necesario para responder con
evidencia real, decilo explícitamente en vez de inventar — ver instrucciones
de formato sobre qué hacer con preguntas sin evidencia suficiente.

La última sección (Gobierno Corporativo, preguntas G1-G6) usa el framework
OECD Principles + UK Corporate Governance Code + criterios ISS/Glass Lewis:
independencia del board, composición, derechos de minoritarios, alineación de
compensación, transparencia/auditoría, e historial en decisiones clave. Es
una sección CUALITATIVA que no cambia trimestre a trimestre (no forma parte
de los refreshes lite). En el campo "notas" de la última pregunta (G6),
además de la evidencia concreta, agregá un resumen de una frase con un rating
de letra (A/B/C/D, con +/- si corresponde) para todo el bloque de gobierno —
ej. "...RATING GOVERNANCE B+: gobierno sólido, sin accionista controlante,
compensación atada a ROIC real."
"""
        + _JSON_FORMAT_INSTRUCTIONS
    )

    system_prompt_lite = (
        """Sos un analista de due diligence. Estás haciendo un REFRESH TRIMESTRAL de
un checklist Pabrai que ya existe — NO estás completando el checklist desde
cero.

Recibís un resumen del estado anterior del checklist completo (para tener
contexto de la situación general de la empresa) y el contexto actualizado de
este trimestre (Agentes 4/7/8-lite: qué cambió financieramente, precio
nuevo, rating actualizado).

Tu tarea: responder SOLO las preguntas de esta lista (todas pertenecen a
secciones numéricas — Apalancamiento, Valoración, Contabilidad, y a veces
Ciclicidad — que son las que cambian balance a balance). Las preguntas de
Moat, Management, Comprensión del negocio, Laboral, ESG, Disciplina Dhandho
y Sesgos NO están en esta lista porque no cambian trimestre a trimestre —
no las respondas, no existen en tu contexto de todas formas.

Si algo en los datos de este trimestre sugiere que una sección NO tocada
(especialmente Moat o Management) podría haber cambiado de forma material,
decilo explícitamente al principio con el texto "🚩 RECOMIENDO REVISAR
[sección]: [motivo]" antes del bloque JSON — igual que hacen los Agentes
4/7/8-lite con la bandera de corrida FULL.
"""
        + _JSON_FORMAT_INSTRUCTIONS
    )

    def build_user_prompt(self, company: str) -> str:
        return f"Compañía a analizar: **{company}**\n\nCompletá el checklist completo (todas las preguntas de la plantilla, incluida la sección de Gobierno Corporativo)."

    def build_user_prompt_lite(self, company: str, previous_output: str, context=None) -> str:
        return (
            f"Compañía: **{company}**\n\n"
            "═══ RESUMEN DEL CHECKLIST ANTERIOR (contexto, secciones no tocadas) ═══\n"
            f"{previous_output}\n"
            "═══ FIN RESUMEN ANTERIOR ═══\n\n"
            "Respondé solo las preguntas listadas en el contexto para este refresh."
        )

    # ═══════════════════════ Orquestación: LLM + escritura del .xlsx ═══════════════════════

    def run_full(
        self,
        company: str,
        context: dict[str, str],
        workbook_path: str,
        sheet_name: str,
        company_header: str,
        summary_line: str,
        fecha_label: str,
    ) -> tuple[str, dict]:
        """Corrida FULL: arma el listado completo de preguntas desde la plantilla del
        propio workbook (número dinámico, no hardcodeado), se lo pasa al LLM vía
        contexto, valida la respuesta, y la escribe en el .xlsx. Retorna
        (texto_para_reporte, resumen_panel)."""
        wb = openpyxl.load_workbook(workbook_path)
        questions = load_question_schema(wb)
        expected_ids = {q.id for q in questions}

        preguntas_texto = "\n".join(f"{q.id}. [{q.seccion}] {q.pregunta}" for q in questions)
        full_context = {**context, f"PREGUNTAS A RESPONDER ({len(questions)}, checklist completo)": preguntas_texto}

        raw = self.run(company, context=full_context, mode="full")
        data = extract_json_block(raw)
        issues = validate_pabrai_answers(data, expected_ids) if data is not None else [
            "No se encontró (o no se pudo parsear) el bloque JSON de respuestas."
        ]

        answers = self._to_answers_dict(data) if data else {}
        resumen = apply_full_checklist(
            workbook_path, sheet_name, company_header, summary_line, answers, fecha_label
        )

        report_text = self._build_report_text(resumen, issues)
        return report_text, resumen

    def run_lite(
        self,
        company: str,
        context: dict[str, str],
        workbook_path: str,
        sheet_name: str,
        previous_summary: str,
        fecha_label: str,
        include_ciclicidad: bool = False,
    ) -> tuple[str, dict]:
        """Refresh lite: arma el subconjunto de preguntas (Apalancamiento +
        Valoración + Contabilidad, + Ciclicidad opcional), valida, y agrega el
        bloque nuevo de columnas al .xlsx existente."""
        wb = openpyxl.load_workbook(workbook_path)
        questions = load_question_schema(wb)

        touched_sections_prefixes = ("1.", "4.", "8.")
        if include_ciclicidad:
            touched_sections_prefixes = touched_sections_prefixes + ("9.",)
        lite_questions = [q for q in questions if q.seccion.startswith(touched_sections_prefixes)]
        expected_ids = {q.id for q in lite_questions}

        preguntas_texto = "\n".join(f"{q.id}. [{q.seccion}] {q.pregunta}" for q in lite_questions)
        full_context = {**context, "PREGUNTAS A RESPONDER (refresh — solo secciones numéricas)": preguntas_texto}

        raw = self.run(company, context=full_context, mode="lite", previous_output=previous_summary)
        data = extract_json_block(raw)
        issues = validate_pabrai_answers(data, expected_ids) if data is not None else [
            "No se encontró (o no se pudo parsear) el bloque JSON de respuestas."
        ]

        answers = self._to_answers_dict(data) if data else {}
        resumen = apply_lite_refresh(workbook_path, sheet_name, answers, fecha_label)

        report_text = self._build_report_text(resumen, issues)
        return report_text, resumen

    @staticmethod
    def _to_answers_dict(data: dict) -> dict[int, dict]:
        answers: dict[int, dict] = {}
        for r in data.get("respuestas", []):
            if isinstance(r, dict) and isinstance(r.get("id"), int):
                answers[r["id"]] = {
                    "veredicto": r.get("veredicto", ""),
                    "severidad": r.get("severidad", ""),
                    "notas": r.get("notas", ""),
                }
        return answers

    @staticmethod
    def _build_report_text(resumen: dict, issues: list[str]) -> str:
        lines = [
            f"**Checklist Pabrai actualizado** ({resumen.get('preguntas_escritas', 0)}/"
            f"{resumen.get('preguntas_totales', '?')} preguntas de esta corrida).",
            "",
            f"- Showstoppers: {'🛑 ' + str(resumen['showstoppers']) if resumen['showstoppers'] else 'Ninguno'}",
            f"- Red flags en secciones críticas (Leverage+Moat+Mgmt): {resumen['red_flags_criticas']}",
            f"- Red flags en secciones secundarias: {resumen['red_flags_secundarias']}",
            f"- Preguntas sin responder: {len(resumen['sin_responder']) or 'Ninguna'}",
            f"- **Sizing recomendado: {resumen['sizing_recomendado']}**",
            f"- Decisión sugerida: {resumen['decision_sugerida']}",
        ]
        text = "\n".join(lines)
        return annotate_with_warnings(text, issues, title="Validación automática del checklist Pabrai")
