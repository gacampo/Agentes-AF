#!/usr/bin/env python3
"""
Agentes-AF: Sistema multi-agente de análisis de inversión.

Orquesta 8 agentes especializados para analizar una compañía
y determinar si es viable para invertir.
"""

from __future__ import annotations

import argparse
import os
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


def run_analysis(company: str, output_dir: str | None = None) -> dict[str, str]:
    """Ejecuta el pipeline completo de análisis para una compañía.

    Fase 1 (Agentes 1-5): Análisis independiente en paralelo conceptual.
    Fase 2 (Agente 6): Pensamiento multidisciplinario con contexto de fase 1.
    Fase 3 (Agente 7): Consolidación de todos los hallazgos.
    Fase 4 (Agente 8): Tesis de inversión final.
    Fase 5 (Agente 9): Decisión de alocación al portafolio.
    Fase 6 (Agente 10): Auditoría QA contra catálogo de checks.
    """
    results: dict[str, str] = {}

    # === Fase 1: Agentes independientes (1-5) ===
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

    # Fase 1
    console.print("\n[bold yellow]═══ Fase 1: Análisis fundamental (Agentes 1-5) ═══[/bold yellow]\n")
    for agent in phase1_agents:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[bold green]{agent.name}[/bold green] analizando..."),
            console=console,
        ) as progress:
            task = progress.add_task("", total=None)
            start = time.time()
            result = agent.run(company)
            elapsed = time.time() - start

        results[agent.name] = result
        console.print(f"  ✓ {agent.name} completado ({elapsed:.1f}s)\n")

    # Fase 2: Multidisciplinary Thinking (necesita contexto de fase 1)
    console.print("\n[bold yellow]═══ Fase 2: Pensamiento multidisciplinario (Agente 6) ═══[/bold yellow]\n")
    agent6 = MultidisciplinaryThinking()
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[bold green]{agent6.name}[/bold green] pensando..."),
        console=console,
    ) as progress:
        task = progress.add_task("", total=None)
        start = time.time()
        result = agent6.run(company, context=results)
        elapsed = time.time() - start
    results[agent6.name] = result
    console.print(f"  ✓ {agent6.name} completado ({elapsed:.1f}s)\n")

    # Fase 3: Organizador Principal (consolida todo)
    console.print("\n[bold yellow]═══ Fase 3: Consolidación (Agente 7) ═══[/bold yellow]\n")
    agent7 = OrganizadorPrincipal()
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[bold green]{agent7.name}[/bold green] consolidando..."),
        console=console,
    ) as progress:
        task = progress.add_task("", total=None)
        start = time.time()
        result = agent7.run(company, context=results)
        elapsed = time.time() - start
    results[agent7.name] = result
    console.print(f"  ✓ {agent7.name} completado ({elapsed:.1f}s)\n")

    # Fase 4: Consejo de Especialistas (tesis final)
    console.print("\n[bold yellow]═══ Fase 4: Tesis de inversión (Agente 8) ═══[/bold yellow]\n")
    agent8 = ConsejoDeEspecialistas()
    # El consejo recibe el resumen del organizador + todo el contexto previo
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[bold green]{agent8.name}[/bold green] deliberando..."),
        console=console,
    ) as progress:
        task = progress.add_task("", total=None)
        start = time.time()
        result = agent8.run(company, context=results)
        elapsed = time.time() - start
    results[agent8.name] = result
    console.print(f"  ✓ {agent8.name} completado ({elapsed:.1f}s)\n")

    # Fase 5: Portfolio Manager (decisión de alocación)
    console.print("\n[bold yellow]═══ Fase 5: Decisión de portafolio (Agente 9) ═══[/bold yellow]\n")
    agent9 = PortfolioManager()
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[bold green]{agent9.name}[/bold green] evaluando alocación..."),
        console=console,
    ) as progress:
        task = progress.add_task("", total=None)
        start = time.time()
        result = agent9.run(company, context=results)
        elapsed = time.time() - start
    results[agent9.name] = result
    console.print(f"  ✓ {agent9.name} completado ({elapsed:.1f}s)\n")

    # Fase 6: QA Reviewer (auditoría contra catálogo)
    console.print("\n[bold yellow]═══ Fase 6: Auditoría QA (Agente 10) ═══[/bold yellow]\n")
    agent10 = QAReviewer()
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[bold green]{agent10.name}[/bold green] auditando..."),
        console=console,
    ) as progress:
        task = progress.add_task("", total=None)
        start = time.time()
        result = agent10.run(company, context=results)
        elapsed = time.time() - start
    results[agent10.name] = result
    console.print(f"  ✓ {agent10.name} completado ({elapsed:.1f}s)\n")

    # Guardar resultados
    if output_dir:
        save_results(company, results, output_dir)

    # Mostrar resultado final: tesis + decisión de portafolio + auditoría QA
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


def save_results(company: str, results: dict[str, str], output_dir: str) -> None:
    """Guarda los resultados de cada agente en archivos individuales y un consolidado."""
    safe_name = company.lower().replace(" ", "_").replace("/", "_")
    base_path = Path(output_dir) / safe_name
    base_path.mkdir(parents=True, exist_ok=True)

    agent_file_names = {
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

    for agent_name, content in results.items():
        filename = agent_file_names.get(agent_name, f"{agent_name}.md")
        filepath = base_path / filename
        filepath.write_text(f"# {agent_name} — {company}\n\n{content}\n", encoding="utf-8")

    # Reporte completo
    full_report = base_path / "reporte_completo.md"
    with full_report.open("w", encoding="utf-8") as f:
        f.write(f"# Análisis de inversión: {company}\n\n")
        f.write("---\n\n")
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

    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[bold red]Error: ANTHROPIC_API_KEY no está configurada.[/bold red]")
        console.print("Configurá tu API key: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    output_dir = None if args.no_save else args.output
    run_analysis(args.company, output_dir)


if __name__ == "__main__":
    main()
