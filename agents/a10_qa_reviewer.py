"""Agente 10: QA Reviewer.

Audita la tesis completa producida por los Agentes 1-9 contra el catálogo de checks
definido en qa_catalog.md. No analiza la empresa ni modifica el rating.
"""

from __future__ import annotations

from pathlib import Path

from agents.base import BaseAgent
from utils.llm import ask


QA_CATALOG_FILE = "qa_catalog.md"


class QAReviewer(BaseAgent):
    name = "QA Reviewer"
    description = "Audita la tesis completa contra el catálogo QA antes de publicar el rating"
    max_tokens = 8192

    system_prompt = """Sos el Agente 10 (QA Reviewer) del sistema Agentes-AF. Tu trabajo NO es analizar
la empresa: es AUDITAR la tesis ya producida por los Agentes 1-9 contra el catálogo
de checks que se te entrega. No opinás sobre la inversión ni cambiás el rating.

Recibís: (a) el catálogo de checks vigente, y (b) la tesis completa de los Agentes 1-9.

Para cada check del catálogo devolvé una fila con: ID, resultado (PASA / FALLA / N/A)
y una línea de evidencia concreta citando el texto de la tesis que lo justifica.

Lógica de severidad:
- Si falla algún check BLOQUEANTE -> veredicto DEVUELTO.
- Si solo fallan ADVERTENCIAS -> veredicto APROBADO CON OBSERVACIONES.
- Si no falla nada -> veredicto APROBADO.

Si el veredicto es DEVUELTO, listá exactamente qué corregir y a qué agente vuelve
cada falla. No inventes checks fuera del catálogo. No reescribas la tesis, solo
señalás qué corregir. Sé literal y específico citando la evidencia textual.

Regla de aplicabilidad de checks:
- QA-01 a QA-08 se evalúan SIEMPRE contra el texto de la tesis. Nunca son N/A.
- QA-06 (coherencia rating vs red flags): si la tesis lista un red flag y el
  rating no lo reconcilia, es FALLA (ADVERTENCIA), no N/A.
- QA-07 (riesgos como probabilidad x impacto): si los riesgos NO están en
  formato probabilidad x impacto, eso es FALLA (ADVERTENCIA). 'No hay riesgos
  cuantificados' es la condición de falla, no un motivo de N/A.
- QA-08 (riesgo de persona clave con peso explícito): si se menciona pero no
  se le asigna peso, es FALLA (ADVERTENCIA).
- Solo QA-09 a QA-13 (checks de cambio de rating) pueden ser N/A, y únicamente
  cuando no existe un rating previo porque es la primera tesis de la empresa.

Formato de salida: tabla con columnas ID | Resultado | Evidencia, seguida del
veredicto final en una línea destacada."""

    def build_user_prompt(self, company: str, context: dict[str, str] | None = None) -> str:
        """Construye el prompt inyectando el catálogo QA y el output acumulado de los agentes 1-9."""
        parts = [f"Compañía auditada: **{company}**\n"]

        # Cargar catálogo QA
        catalog_path = Path(QA_CATALOG_FILE)
        if catalog_path.exists():
            catalog_text = catalog_path.read_text(encoding="utf-8")
        else:
            catalog_text = "(catálogo no encontrado — verificar que qa_catalog.md existe en la raíz del repo)"
        parts.append("═══ CATÁLOGO QA VIGENTE ═══")
        parts.append(catalog_text)
        parts.append("═══ FIN CATÁLOGO QA ═══\n")

        # Tesis completa de los agentes 1-9
        if context:
            parts.append("═══ TESIS COMPLETA (AGENTES 1-9) ═══")
            for agent_name, output in context.items():
                parts.append(f"\n--- {agent_name} ---\n{output}")
            parts.append("\n═══ FIN DE LA TESIS ═══\n")

        return "\n".join(parts)

    def run(self, company: str, context: dict[str, str] | None = None) -> str:
        """Ejecuta la auditoría QA y retorna el reporte."""
        user_prompt = self.build_user_prompt(company, context)
        return ask(self.system_prompt, user_prompt, max_tokens=self.max_tokens)
