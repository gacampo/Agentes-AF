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
    model = "claude-haiku-4-5-20251001"
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
- QA-14 (precio de mercado actual) se evalúa SIEMPRE. Nunca es N/A. Falla si
  cualquier agente cita precios stale o en base pre-split en lugar del precio
  provisto por el usuario.
- QA-15 (coherencia aritmética de valoración) se evalúa SIEMPRE. Nunca es N/A.
  Falla si una afirmación cualitativa (descuento, premium, margen de seguridad)
  contradice los números presentados. Ej: decir "descuento al NAV" cuando
  precio > NAV-mid es FALLA BLOQUEANTE.
- QA-18 (descuento de holding) es N/A únicamente si la empresa NO es un
  holding/conglomerado/trust/REIT con NAV o valor intrínseco autoevaluado
  publicado por la propia compañía — para cualquier empresa de ese tipo se
  evalúa SIEMPRE. Falla (BLOQUEANTE) si algún escenario de la sección 8,
  incluido el optimista, asume que el mercado converge al 100% o más de esa
  cifra sin que la tesis cite evidencia concreta de que el descuento de esa
  empresa (o de un catalizador comparable ya ejecutado, ej. un spin-off que
  buscaba resolverlo) cerró de forma sostenida en el pasado.

Formato de salida: tabla con columnas ID | Resultado | Evidencia, seguida del
veredicto final en una línea destacada."""

    def build_user_prompt(self, company: str) -> str:
        """Construye el prompt inyectando el catálogo QA. El contexto acumulado
        llega por separado como bloque cacheado via build_cached_context()."""
        parts = [f"Compañía auditada: **{company}**\n"]

        catalog_path = Path(QA_CATALOG_FILE)
        if catalog_path.exists():
            catalog_text = catalog_path.read_text(encoding="utf-8")
        else:
            catalog_text = "(catálogo no encontrado — verificar que qa_catalog.md existe en la raíz del repo)"
        parts.append("═══ CATÁLOGO QA VIGENTE ═══")
        parts.append(catalog_text)
        parts.append("═══ FIN CATÁLOGO QA ═══\n")

        return "\n".join(parts)
