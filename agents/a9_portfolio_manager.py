"""Agente 9: Portfolio Manager.

Determina si una compañía ingresa al portafolio y con qué porcentaje de alocación,
basándose en la tesis de inversión completa y el estado actual del portafolio.
Mantiene restricciones estrictas de diversificación y pondera por convicción y descuento al valor justo.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.base import BaseAgent
from utils.llm import ask


PORTFOLIO_FILE = "reportes/portafolio.json"

DEFAULT_PORTFOLIO = {
    "posiciones": [],
    "cash_disponible_pct": 100.0,
    "reglas": {
        "max_por_empresa_pct": 10.0,
        "max_por_sector_pct": 25.0,
        "max_por_pais_pct": 25.0,
        "min_posicion_pct": 1.0,
    },
}


def load_portfolio(path: str = PORTFOLIO_FILE) -> dict:
    """Carga el portafolio existente o crea uno nuevo."""
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(json.dumps(DEFAULT_PORTFOLIO))


def save_portfolio(portfolio: dict, path: str = PORTFOLIO_FILE) -> None:
    """Guarda el portafolio actualizado."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8")


class PortfolioManager(BaseAgent):
    name = "Portfolio Manager"
    description = "Decide alocación al portafolio basándose en convicción, descuento al fair value y diversificación."
    max_tokens = 8192

    system_prompt = """Sos el Portfolio Manager del fondo de inversión. Tu rol es tomar la decisión FINAL
de si una compañía ingresa al portafolio y con qué porcentaje de alocación.

═══ REGLAS ESTRICTAS DE ALOCACIÓN ═══

1. **Máximo por empresa**: 10% del portafolio. Ninguna posición individual puede superar este límite.
2. **Máximo por sector/industria**: 25% del portafolio en un mismo sector.
3. **Máximo por país**: 25% del portafolio en un mismo país.
4. **Mínimo por posición**: 1%. Si la convicción no justifica al menos 1%, la empresa NO entra al portafolio.
5. **El porcentaje total del portafolio nunca puede superar 100%.**

═══ CRITERIOS DE PONDERACIÓN ═══

El porcentaje alocado debe basarse en:

1. **Descuento al valor justo (fair value)**: Empresas con mayor margen de seguridad
   (mayor descuento respecto a su valoración intrínseca) deben pesar MÁS en el portafolio.
   Esta es la variable más importante.

2. **Nivel de convicción**: Basado en:
   - Calidad del modelo de negocio y durabilidad
   - Fortaleza de las ventajas competitivas
   - Calidad del management
   - Predictibilidad de los flujos de caja
   - Consenso positivo del análisis de los agentes anteriores

3. **Relación riesgo/retorno**: La TIR esperada vs. los riesgos identificados.

4. **Diversificación**: Considerar las posiciones existentes para mantener equilibrio
   por sector, geografía y tipo de negocio.

═══ FORMATO DE DECISIÓN ═══

Tu output debe incluir:

1. **Decisión**: INGRESA / NO INGRESA al portafolio
2. **Porcentaje alocado**: X% (justificado)
3. **Datos de clasificación**:
   - Ticker
   - Sector/Industria
   - País principal
   - Precio actual aproximado
   - Valor intrínseco estimado (del análisis previo)
   - Descuento/Prima al fair value
4. **Justificación de la alocación**: Por qué ese porcentaje y no más o menos.
   Referenciá los escenarios y TIR del agente de valoración.
5. **Condiciones de salida**: Bajo qué circunstancias se debería vender o reducir la posición.
6. **Estado actualizado del portafolio**: Tabla con todas las posiciones actuales
   incluyendo la nueva (si ingresa), mostrando:
   | Empresa | Ticker | Sector | País | Alocación % | Descuento al FV |
7. **Concentración por sector y país**: Verificar que ningún sector/país supere 25%.
8. **Cash restante**: Porcentaje disponible para futuras posiciones.

═══ IMPORTANTE ═══

- No repitas ni re-narres el análisis de los agentes anteriores; asumí que el lector ya tiene
  ese contexto. Aportá únicamente tu decisión de alocación y su justificación. Sin preámbulos
  ni relleno.
- Si la empresa no tiene suficiente margen de seguridad o la convicción es baja, NO la incluyas.
  Es mejor tener cash que una mala posición.
- Sé disciplinado y riguroso. Un buen portfolio manager dice "no" más de lo que dice "sí".
- Fundamentá CADA decisión con datos concretos del análisis previo.
- Si incluir esta empresa violaría algún límite de concentración, ajustá o rechazá.
- Respondé en español.
- Formato: Markdown profesional.
- Esto NO es asesoramiento financiero."""

    def build_user_prompt(self, company: str) -> str:
        """Construye el prompt con el estado actual del portafolio. El contexto acumulado
        llega por separado como bloque cacheado via build_cached_context()."""
        parts = [f"Compañía evaluada: **{company}**\n"]

        portfolio = load_portfolio()
        parts.append("═══ ESTADO ACTUAL DEL PORTAFOLIO ═══")
        if portfolio["posiciones"]:
            parts.append(f"Posiciones actuales: {len(portfolio['posiciones'])}")
            parts.append(f"Cash disponible: {portfolio['cash_disponible_pct']:.1f}%\n")
            parts.append("| Empresa | Ticker | Sector | País | Alocación % | Descuento FV |")
            parts.append("|---------|--------|--------|------|-------------|--------------|")
            for pos in portfolio["posiciones"]:
                parts.append(
                    f"| {pos['empresa']} | {pos['ticker']} | {pos['sector']} "
                    f"| {pos['pais']} | {pos['alocacion_pct']}% | {pos.get('descuento_fv', 'N/A')} |"
                )
            sector_totals: dict[str, float] = {}
            country_totals: dict[str, float] = {}
            for pos in portfolio["posiciones"]:
                sector_totals[pos["sector"]] = sector_totals.get(pos["sector"], 0) + pos["alocacion_pct"]
                country_totals[pos["pais"]] = country_totals.get(pos["pais"], 0) + pos["alocacion_pct"]
            parts.append(f"\nConcentración por sector: {json.dumps(sector_totals, ensure_ascii=False)}")
            parts.append(f"Concentración por país: {json.dumps(country_totals, ensure_ascii=False)}")
        else:
            parts.append("El portafolio está VACÍO. Esta sería la primera posición potencial.")
            parts.append(f"Cash disponible: {portfolio['cash_disponible_pct']:.1f}%")

        parts.append(f"\nReglas: {json.dumps(portfolio['reglas'], ensure_ascii=False)}")
        parts.append("═══ FIN ESTADO PORTAFOLIO ═══\n")

        return "\n".join(parts)
