#!/usr/bin/env python3
"""
Agentes-AF: Sistema multi-agente de análisis de inversión.

Orquesta 8 agentes especializados para analizar una compañía
y determinar si es viable para invertir.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from agents import (
    BusinessModelClarifier,
    LeadershipCapitalAllocation,
    CompetitiveAdvantagesDynamics,
    PrimaryResearchAnalyst,
    CustomerValueDurability,
    MultidisciplinaryThinking,
    OrganizadorPrincipal,
    ConsejoDeEspecialistas,
    PortfolioManager,
)
from agents.a10_qa_reviewer import QAReviewer

console = Console()

# Mapeo canónico agente → archivo de salida (usado para resumibilidad)
AGENT_FILE_NAMES: dict[str, str] = {
    "Business Model Clarifier": "01_modelo_negocio.md",
    "Leadership & Capital Allocation": "02_liderazgo.md",
    "Competitive Advantages Dynamics": "03_ventajas_competitivas.md",
    "Primary Research Analyst": "04_investigacion_primaria.md",
    "Customer Value & Durability": "05_valor_cliente.md",
    "Multidisciplinary Thinking": "06_pensamiento_multidisciplinario.md",
    "Organizador Principal": "07_resumen_consolidado.md",
    "El Consejo de los Especialistas": "08_tesis_inversion.md",
    "Portfolio Manager": "09_portfolio_manager.md",
    "QA Reviewer": "10_qa_review.md",
}


def _agent_file_path(base_path: Path, agent_name: str) -> Path:
    filename = AGENT_FILE_NAMES.get(agent_name, f"{agent_name}.md")
    return base_path / filename


def _load_cached(base_path: Path, agent_name: str) -> str | None:
    """Carga la salida de un agente del disco. Retorna None si no existe."""
    path = _agent_file_path(base_path, agent_name)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    # El archivo tiene encabezado "# {agent_name} — {company}\n\n"; lo quitamos
    lines = text.split("\n", 2)
    return lines[2].rstrip("\n") if len(lines) >= 3 else text


def _save_agent(base_path: Path, agent_name: str, company: str, content: str) -> None:
    base_path.mkdir(parents=True, exist_ok=True)
    _agent_file_path(base_path, agent_name).write_text(
        f"# {agent_name} — {company}\n\n{content}\n", encoding="utf-8"
    )


def _build_price_context(precio_actual: float | None, fecha_precio: str, notas_corporativas: str) -> str:
    """Construye el bloque de precio de mercado para inyectar en los agentes."""
    if precio_actual is None:
        return (
            "⚠️ PRECIO DE MERCADO: No se proveyó precio actual. "
            "La tesis debe marcarse como PRELIMINAR y advertir que el precio es estimado."
        )
    notas = notas_corporativas.strip() if notas_corporativas.strip() else "ninguna"
    return (
        f"PRECIO DE MERCADO ACTUAL provisto por el usuario: ${precio_actual:.2f} al {fecha_precio}. "
        f"Ajustado por: {notas}. "
        "Usá ESTE precio como referencia para escenarios, margen de seguridad y TIR. "
        "NO infieras el precio de tus datos de entrenamiento, que pueden estar stale o en base pre-split."
    )


def run_analysis(
    company: str,
    precio_actual: float | None,
    fecha_precio: str,
    notas_corporativas: str,
    output_dir: str | None = None,
    fresh: bool = False,
) -> dict[str, str]:
    """Ejecuta el pipeline completo de análisis para una compañía.

    Fase 1 (Agentes 1-5): Análisis independiente en paralelo conceptual.
    Fase 2 (Agente 6): Pensamiento multidisciplinario con contexto de fase 1.
    Fase 3 (Agente 7): Consolidación de todos los hallazgos.
    Fase 4 (Agente 8): Tesis de inversión final.
    Fase 5 (Agente 9): Decisión de alocación al portafolio.
    Fase 6 (Agente 10): Auditoría QA contra catálogo de checks.

    Si fresh=False (default), los agentes cuyo archivo de salida ya existe en
    output_dir se saltean y se carga su resultado del disco, permitiendo retomar
    una corrida interrumpida desde el punto de corte.
    Si fresh=True, se borran los reportes existentes antes de arrancar.
    """
    base_path = (
        Path(output_dir) / company.lower().replace(" ", "_").replace("/", "_")
        if output_dir
        else None
    )

    if fresh and base_path and base_path.exists():
        shutil.rmtree(base_path)
        console.print(
            f"[bold red]─── Corrida limpia: reportes anteriores de '{company}' eliminados ───[/bold red]\n"
        )

    results: dict[str, str] = {}
    price_context = _build_price_context(precio_actual, fecha_precio, notas_corporativas)
    price_injection: dict[str, str] = {"__precio_mercado__": price_context}

    def run_or_load(agent, context) -> str:
        """Carga del disco si ya existe, si no corre el agente y guarda."""
        if base_path:
            cached = _load_cached(base_path, agent.name)
            if cached is not None:
                console.print(f"  ⏭  {agent.name} [dim](cargado del disco)[/dim]\n")
                return cached
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[bold green]{agent.name}[/bold green] analizando..."),
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            start = time.time()
            result = agent.run(company, context=context)
            elapsed = time.time() - start
        if base_path:
            _save_agent(base_path, agent.name, company, result)
        console.print(f"  ✓ {agent.name} completado ({elapsed:.1f}s)\n")
        return result

    phase1_agents = [
        BusinessModelClarifier(),
        LeadershipCapitalAllocation(),
        CompetitiveAdvantagesDynamics(),
        PrimaryResearchAnalyst(),
        CustomerValueDurability(),
    ]

    console.print(Panel(
        f"[bold cyan]Analizando: {company}[/bold cyan]\n\n"
        "10 agentes especializados trabajarán en secuencia para\n"
        "construir una tesis de inversión integral, decidir alocación al portafolio\n"
        "y auditar la calidad del proceso.",
        title="🔍 Agentes-AF",
        border_style="cyan",
    ))

    console.print("\n[bold yellow]═══ Fase 1: Análisis fundamental (Agentes 1-5) ═══[/bold yellow]\n")
    for agent in phase1_agents:
        results[agent.name] = run_or_load(agent, price_injection)

    console.print("\n[bold yellow]═══ Fase 2: Pensamiento multidisciplinario (Agente 6) ═══[/bold yellow]\n")
    agent6 = MultidisciplinaryThinking()
    results[agent6.name] = run_or_load(agent6, {**results, **price_injection})

    console.print("\n[bold yellow]═══ Fase 3: Consolidación (Agente 7) ═══[/bold yellow]\n")
    agent7 = OrganizadorPrincipal()
    results[agent7.name] = run_or_load(agent7, {**results, **price_injection})

    console.print("\n[bold yellow]═══ Fase 4: Tesis de inversión (Agente 8) ═══[/bold yellow]\n")
    agent8 = ConsejoDeEspecialistas()
    results[agent8.name] = run_or_load(agent8, {**results, **price_injection})

    console.print("\n[bold yellow]═══ Fase 5: Decisión de portafolio (Agente 9) ═══[/bold yellow]\n")
    agent9 = PortfolioManager()
    results[agent9.name] = run_or_load(agent9, {**results, **price_injection})

    console.print("\n[bold yellow]═══ Fase 6: Auditoría QA (Agente 10) ═══[/bold yellow]\n")
    agent10 = QAReviewer()
    results[agent10.name] = run_or_load(agent10, results)

    # Guardar reporte consolidado (los individuales ya se guardaron en run_or_load)
    if base_path:
        _save_full_report(company, results, base_path)

    console.print(Panel(
        Markdown(results["El Consejo de los Especialistas"]),
        title="📋 Tesis de inversión final",
        border_style="green",
    ))
    console.print(Panel(
        Markdown(results["Portfolio Manager"]),
        title="💼 Decisión de portafolio",
        border_style="magenta",
    ))
    console.print(Panel(
        Markdown(results["QA Reviewer"]),
        title="🔎 Auditoría QA",
        border_style="yellow",
    ))

    return results


def _save_full_report(company: str, results: dict[str, str], base_path: Path) -> None:
    """Escribe el reporte consolidado. Los archivos individuales ya se guardaron."""
    full_report = base_path / "reporte_completo.md"
    with full_report.open("w", encoding="utf-8") as f:
        f.write(f"# Análisis de inversión: {company}\n\n---\n\n")
        for agent_name, content in results.items():
            f.write(f"## {agent_name}\n\n{content}\n\n---\n\n")
    console.print(f"\n[bold green]Resultados guardados en: {base_path}[/bold green]")


def main():
    parser = argparse.ArgumentParser(
        description="Agentes-AF: Análisis de inversión multi-agente",
    )
    parser.add_argument(
        "company",
        help="Nombre de la compañía a analizar (ej: 'Apple', 'Mercado Libre', 'Costco')",
    )
    parser.add_argument(
        "-o", "--output",
        default="reportes",
        help="Directorio donde guardar los reportes (default: reportes/)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="No guardar los resultados en archivos",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Forzar corrida limpia: borra reportes existentes de la empresa antes de arrancar",
    )

    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[bold red]Error: ANTHROPIC_API_KEY no está configurada.[/bold red]")
        console.print("Configurá tu API key: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # Inputs de precio de mercado (interactivos)
    console.print("\n[bold cyan]─── Precio de mercado ───[/bold cyan]")
    precio_str = console.input(
        "[yellow]Precio actual de mercado (ej: 54.20) — Enter para omitir: [/yellow]"
    ).strip()
    precio_actual: float | None = None
    if precio_str:
        try:
            precio_actual = float(precio_str.replace(",", "."))
        except ValueError:
            console.print("[red]Precio inválido, se omite.[/red]")

    fecha_precio = ""
    notas_corporativas = ""
    if precio_actual is not None:
        fecha_precio = console.input(
            "[yellow]Fecha del precio (ej: 04-Jun-2026): [/yellow]"
        ).strip()
        notas_corporativas = console.input(
            "[yellow]Notas corporativas (splits, acciones vigentes — Enter para omitir): [/yellow]"
        ).strip()

    output_dir = None if args.no_save else args.output
    run_analysis(args.company, precio_actual, fecha_precio, notas_corporativas, output_dir, fresh=args.fresh)


if __name__ == "__main__":
    main()
