#!/usr/bin/env python3
"""
Agentes-AF: Sistema multi-agente de análisis de inversión.

Orquesta 10 agentes especializados para analizar una compañía,
construir una tesis de inversión, decidir alocación al portafolio,
y auditar la calidad del proceso.

Dos modos de corrida:
- --mode full (default): pipeline completo, los 10 agentes. Empresa nueva,
  o cuando hay un cambio estructural que amerita revisar todo desde cero.
- --mode lite: refresh trimestral. Solo corren en versión "lite" los
  Agentes 4, 7 y 8 (los que dependen de datos que cambian balance a balance);
  los Agentes 1, 2, 3, 5, 6 (la tesis cualitativa) NO se tocan, se mantienen
  tal cual del último full. Los Agentes 9 y 10 corren siempre completos
  porque son livianos y necesitan ver el estado más reciente.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import datetime, timezone
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
from agents.a11_pabrai_checklist import PabraiChecklistAgent
from utils.merge import (
    A7_FASE_B_PATTERN,
    A7_FASE_C_PATTERN,
    A8_SECCION_8_PATTERN,
    A8_SECCION_10_PATTERN,
    extract_section,
    merge_lite_into_full,
)
from utils import history_db
from utils.validation import extract_json_block

console = Console()

# Mapeo canónico agente → archivo de salida (usado para resumibilidad y para
# cargar el estado anterior en modo lite).
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
    "Pabrai Checklist": "11_checklist_pabrai.md",
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


def _require_full_run_exists(base_path: Path, company: str) -> dict[str, str]:
    """Modo lite requiere una corrida full previa completa. Carga y retorna
    todos los outputs anteriores, o corta la ejecución con un mensaje claro
    si falta alguno."""
    previous: dict[str, str] = {}
    faltantes: list[str] = []
    for agent_name in AGENT_FILE_NAMES:
        if agent_name in ("QA Reviewer", "Pabrai Checklist"):
            continue  # QA se regenera siempre; Pabrai es opcional (solo si se pasó --pabrai-xlsx)
        cached = _load_cached(base_path, agent_name)
        if cached is None:
            faltantes.append(agent_name)
        else:
            previous[agent_name] = cached

    if faltantes:
        console.print(
            f"[bold red]Error: no se puede correr --mode lite para '{company}' — "
            f"falta una corrida completa previa.[/bold red]"
        )
        console.print(f"[red]Agentes sin reporte guardado en {base_path}: {', '.join(faltantes)}[/red]")
        console.print("[yellow]Corré primero: python main.py \"" + company + "\" --mode full[/yellow]")
        sys.exit(1)

    return previous


def _pabrai_summary_line(company: str, precio_actual: float | None, fecha_precio: str) -> str:
    """Línea corta de referencia para la celda A2 de la hoja del checklist."""
    if precio_actual is None:
        return f"{company} | Precio no provisto (checklist preliminar) | {fecha_precio or 'sin fecha'}"
    return f"{company} | Precio: {precio_actual:.2f} | Fecha: {fecha_precio or 'sin fecha'}"


def _record_history(company: str, mode: str, results: dict[str, str]) -> None:
    """Extrae precio/rating/decisión de los bloques JSON de los Agentes 8 y 9
    (ya validados por esos agentes) y graba una fila en la base de historial.
    No falla la corrida si algo no se puede parsear — el historial es un
    complemento, no algo de lo que dependa el resultado principal."""
    try:
        a8_data = extract_json_block(results.get("El Consejo de los Especialistas", "")) or {}
        a9_data = extract_json_block(results.get("Portfolio Manager", "")) or {}
        rating = a8_data.get("rating", {}) if isinstance(a8_data, dict) else {}

        history_db.record_run(
            company=company,
            mode=mode,
            ticker=a9_data.get("ticker") if isinstance(a9_data, dict) else None,
            sector=a9_data.get("sector") if isinstance(a9_data, dict) else None,
            pais=a9_data.get("pais") if isinstance(a9_data, dict) else None,
            fecha=rating.get("fecha_rating"),
            precio_referencia=rating.get("precio_referencia"),
            calidad_negocio=rating.get("calidad_negocio"),
            atractivo_valoracion=rating.get("atractivo_valoracion"),
            rating_compuesto=rating.get("rating_compuesto"),
            decision_portafolio=a9_data.get("decision") if isinstance(a9_data, dict) else None,
            alocacion_pct=a9_data.get("alocacion_pct") if isinstance(a9_data, dict) else None,
        )
    except Exception as e:  # noqa: BLE001 - el historial nunca debe romper la corrida principal
        console.print(f"  [yellow]⚠ No se pudo grabar el historial de esta corrida: {e}[/yellow]\n")


def run_analysis(
    company: str,
    precio_actual: float | None,
    fecha_precio: str,
    notas_corporativas: str,
    output_dir: str | None = None,
    fresh: bool = False,
    mode: str = "full",
    hecho_nuevo: str = "",
    pabrai_xlsx: str | None = None,
    pabrai_sheet: str | None = None,
) -> dict[str, str]:
    """Ejecuta el pipeline de análisis para una compañía, en modo full o lite.

    Si fresh=False (default) en modo full, los agentes cuyo archivo de salida
    ya existe en output_dir se saltean y se carga su resultado del disco,
    permitiendo retomar una corrida interrumpida desde el punto de corte.
    Si fresh=True, se borran los reportes existentes antes de arrancar
    (no válido junto con mode="lite").
    """
    if mode not in ("full", "lite"):
        raise ValueError(f"mode debe ser 'full' o 'lite', recibido: {mode!r}")
    if mode == "lite" and fresh:
        console.print("[bold red]Error: --fresh no es compatible con --mode lite.[/bold red]")
        sys.exit(1)
    if mode == "lite" and not output_dir:
        console.print("[bold red]Error: --mode lite requiere guardar/leer reportes (no usar --no-save).[/bold red]")
        sys.exit(1)

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

    price_context = _build_price_context(precio_actual, fecha_precio, notas_corporativas)
    price_injection: dict[str, str] = {"__precio_mercado__": price_context}
    if hecho_nuevo.strip():
        price_injection["__hecho_nuevo__"] = hecho_nuevo.strip()

    console.print(Panel(
        f"[bold cyan]Analizando: {company}[/bold cyan]  [dim](modo: {mode})[/dim]\n\n"
        + (
            "10 agentes especializados trabajarán en secuencia para\n"
            "construir una tesis de inversión integral, decidir alocación al portafolio\n"
            "y auditar la calidad del proceso."
            if mode == "full"
            else
            "Refresh trimestral: solo se recalculan los datos que cambian\n"
            "balance a balance (Agentes 4, 7 y 8). La tesis cualitativa\n"
            "(Agentes 1-3, 5-6) se mantiene del último análisis completo."
        ),
        title="🔍 Agentes-AF",
        border_style="cyan",
    ))

    if mode == "lite":
        results = run_analysis_lite(
            company, base_path, price_injection, precio_actual, fecha_precio,
            pabrai_xlsx=pabrai_xlsx, pabrai_sheet=pabrai_sheet,
        )
    else:
        results = run_analysis_full(
            company, base_path, price_injection, precio_actual, fecha_precio,
            pabrai_xlsx=pabrai_xlsx, pabrai_sheet=pabrai_sheet,
        )

    _record_history(company, mode, results)

    if base_path:
        _save_full_report(company, results, base_path)

    console.print(Panel(
        Markdown(results["El Consejo de los Especialistas"]),
        title="📋 Tesis de inversión (vigente)",
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
    if "Pabrai Checklist" in results:
        console.print(Panel(
            Markdown(results["Pabrai Checklist"]),
            title="✅ Checklist Pabrai",
            border_style="blue",
        ))

    return results


def _run_pabrai_checklist(
    company: str,
    results: dict[str, str],
    base_path: Path | None,
    price_injection: dict[str, str],
    precio_actual: float | None,
    fecha_precio: str,
    pabrai_xlsx: str | None,
    pabrai_sheet: str | None,
    mode: str,
) -> str | None:
    """Corre el Agente 11 (full o lite) si se configuró --pabrai-xlsx. Es
    complementario al pipeline principal: si algo falla acá (archivo
    corrupto, hoja inexistente en lite, etc.) se loguea un warning claro y
    se sigue — no debe tirar abajo una tesis que ya se generó bien."""
    if not pabrai_xlsx:
        return None

    sheet_name = pabrai_sheet or company
    fecha_label = fecha_precio or time.strftime("%d-%b-%Y")
    agent11 = PabraiChecklistAgent()
    context = {**results, **price_injection}

    console.print(f"\n[bold yellow]═══ Fase 7: Checklist Pabrai (Agente 11, {mode}) ═══[/bold yellow]\n")
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[bold green]{agent11.name}[/bold green] ({mode})..."),
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            start = time.time()
            if mode == "full":
                report, resumen = agent11.run_full(
                    company,
                    context=context,
                    workbook_path=pabrai_xlsx,
                    sheet_name=sheet_name,
                    company_header=f"CHECKLIST PABRAI — {company.upper()}",
                    summary_line=_pabrai_summary_line(company, precio_actual, fecha_precio),
                    fecha_label=f"FULL-{fecha_label}",
                )
            else:
                previous_summary = _load_cached(base_path, "Pabrai Checklist") if base_path else None
                if previous_summary is None:
                    console.print(
                        "  [yellow]⚠ No hay checklist Pabrai previo guardado para esta empresa — "
                        "corré primero --mode full con --pabrai-xlsx para poder hacer el refresh. "
                        "Se omite el Agente 11 en esta corrida.[/yellow]\n"
                    )
                    return None
                report, resumen = agent11.run_lite(
                    company,
                    context=context,
                    workbook_path=pabrai_xlsx,
                    sheet_name=sheet_name,
                    previous_summary=previous_summary,
                    fecha_label=fecha_label,
                )
            elapsed = time.time() - start
        console.print(f"  ✓ {agent11.name} completado ({elapsed:.1f}s)\n")
        if base_path:
            _save_agent(base_path, agent11.name, company, report)
        return report
    except Exception as e:  # noqa: BLE001 - deliberadamente amplio: es un paso opcional
        console.print(f"  [bold red]⚠ Checklist Pabrai falló, se omite: {e}[/bold red]\n")
        return None


def run_analysis_full(
    company: str,
    base_path: Path | None,
    price_injection: dict[str, str],
    precio_actual: float | None = None,
    fecha_precio: str = "",
    pabrai_xlsx: str | None = None,
    pabrai_sheet: str | None = None,
) -> dict[str, str]:
    """Pipeline completo: los 10 agentes en secuencia (comportamiento original)."""
    results: dict[str, str] = {}

    def run_or_load(agent, context) -> str:
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

    pabrai_report = _run_pabrai_checklist(
        company, results, base_path, price_injection, precio_actual, fecha_precio,
        pabrai_xlsx, pabrai_sheet, mode="full",
    )
    if pabrai_report:
        results["Pabrai Checklist"] = pabrai_report

    return results


def run_analysis_lite(
    company: str,
    base_path: Path | None,
    price_injection: dict[str, str],
    precio_actual: float | None = None,
    fecha_precio: str = "",
    pabrai_xlsx: str | None = None,
    pabrai_sheet: str | None = None,
) -> dict[str, str]:
    """Refresh trimestral: solo corren en modo lite los Agentes 4, 7 y 8.
    Los Agentes 1, 2, 3, 5, 6 se cargan tal cual del último full. Los
    Agentes 9 y 10 corren completos (son livianos y necesitan ver lo último)."""
    assert base_path is not None  # ya validado en run_analysis()
    previous = _require_full_run_exists(base_path, company)
    results: dict[str, str] = {}

    # Agentes 1, 2, 3, 5, 6: se mantienen del último full, sin re-narrar.
    for agent_name in [
        "Business Model Clarifier",
        "Leadership & Capital Allocation",
        "Competitive Advantages Dynamics",
        "Customer Value & Durability",
        "Multidisciplinary Thinking",
    ]:
        results[agent_name] = previous[agent_name]
        console.print(f"  ⏭  {agent_name} [dim](tesis cualitativa vigente, sin cambios)[/dim]\n")

    def timed_run(agent, **kwargs) -> str:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[bold green]{agent.name}[/bold green] (refresh)..."),
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            start = time.time()
            result = agent.run(company, **kwargs)
            elapsed = time.time() - start
        console.print(f"  ✓ {agent.name} refresh completado ({elapsed:.1f}s)\n")
        return result

    console.print("\n[bold yellow]═══ Refresh 1: Investigación primaria (Agente 4-lite) ═══[/bold yellow]\n")
    agent4 = PrimaryResearchAnalyst()
    a4_delta = timed_run(
        agent4, context=price_injection, mode="lite", previous_output=previous["Primary Research Analyst"]
    )
    a4_full_doc = (
        a4_delta.strip()
        + "\n\n---\n\n> 📜 **Investigación anterior (histórica):**\n\n"
        + previous["Primary Research Analyst"]
    )
    if base_path:
        _save_agent(base_path, agent4.name, company, a4_full_doc)
    results[agent4.name] = a4_full_doc

    console.print("\n[bold yellow]═══ Refresh 2: Métricas y valoración (Agente 7-lite) ═══[/bold yellow]\n")
    agent7 = OrganizadorPrincipal()
    prev_fase_b = extract_section(previous["Organizador Principal"], A7_FASE_B_PATTERN, A7_FASE_C_PATTERN)
    a7_delta = timed_run(
        agent7,
        context={
            **price_injection,
            "Primary Research Analyst — cambios de este trimestre": a4_delta,
        },
        mode="lite",
        previous_output=prev_fase_b,
    )
    a7_full_doc, merge7_ok = merge_lite_into_full(
        previous["Organizador Principal"], a7_delta, A7_FASE_B_PATTERN, A7_FASE_C_PATTERN
    )
    if not merge7_ok:
        console.print("  [bold red]⚠ No se pudo fusionar automáticamente la Fase B — revisar el archivo a mano.[/bold red]\n")
    if base_path:
        _save_agent(base_path, agent7.name, company, a7_full_doc)
    results[agent7.name] = a7_full_doc

    console.print("\n[bold yellow]═══ Refresh 3: Escenarios y rating (Agente 8-lite) ═══[/bold yellow]\n")
    agent8 = ConsejoDeEspecialistas()
    a8_delta = timed_run(
        agent8,
        context={
            **price_injection,
            "Primary Research Analyst — cambios de este trimestre": a4_delta,
            "Organizador Principal — Fase B actualizada": a7_delta,
        },
        mode="lite",
        previous_output=previous["El Consejo de los Especialistas"],
    )
    a8_full_doc, merge8_ok = merge_lite_into_full(
        previous["El Consejo de los Especialistas"], a8_delta, A8_SECCION_8_PATTERN, A8_SECCION_10_PATTERN
    )
    if not merge8_ok:
        console.print("  [bold red]⚠ No se pudo fusionar automáticamente la sección 8-9 — revisar el archivo a mano.[/bold red]\n")
    if base_path:
        _save_agent(base_path, agent8.name, company, a8_full_doc)
    results[agent8.name] = a8_full_doc

    console.print("\n[bold yellow]═══ Fase 5: Decisión de portafolio (Agente 9, completo) ═══[/bold yellow]\n")
    agent9 = PortfolioManager()
    results[agent9.name] = timed_run(agent9, context={**results, **price_injection}, mode="full")
    if base_path:
        _save_agent(base_path, agent9.name, company, results[agent9.name])

    console.print("\n[bold yellow]═══ Fase 6: Auditoría QA (Agente 10, completo) ═══[/bold yellow]\n")
    agent10 = QAReviewer()
    results[agent10.name] = timed_run(agent10, context=results, mode="full")
    if base_path:
        _save_agent(base_path, agent10.name, company, results[agent10.name])

    pabrai_report = _run_pabrai_checklist(
        company, results, base_path, price_injection, precio_actual, fecha_precio,
        pabrai_xlsx, pabrai_sheet, mode="lite",
    )
    if pabrai_report:
        results["Pabrai Checklist"] = pabrai_report

    return results


def _save_full_report(company: str, results: dict[str, str], base_path: Path) -> None:
    """Escribe el reporte consolidado. Los archivos individuales ya se guardaron."""
    full_report = base_path / "reporte_completo.md"
    with full_report.open("w", encoding="utf-8") as f:
        f.write(f"# Análisis de inversión: {company}\n\n---\n\n")
        for agent_name, content in results.items():
            f.write(f"## {agent_name}\n\n{content}\n\n---\n\n")
    console.print(f"\n[bold green]Resultados guardados en: {base_path}[/bold green]")


def _get_current_price(ticker: str) -> float | None:
    """Consulta el precio actual vía yfinance (gratis, sin tokens de LLM).
    Retorna None si falla (ticker inválido, sin conexión, etc.) — el
    llamador debe manejar ese caso sin romper el chequeo de las demás
    empresas."""
    try:
        import yfinance as yf
    except ImportError:
        console.print(
            "[bold red]Falta yfinance. Instalalo con: pip install yfinance[/bold red]"
        )
        return None
    try:
        info = yf.Ticker(ticker).fast_info
        price = info.get("lastPrice") or info.get("last_price")
        return float(price) if price else None
    except Exception:
        return None


def _deep_structural_check(company: str, ticker: str, fecha_ultima_corrida: str) -> str | None:
    """Chequeo opcional (--deep): una búsqueda web barata para detectar
    eventos estructurales (cambio de CEO, M&A) desde la última corrida.
    Cuesta ~$0.01-0.03 por empresa — no corre por default."""
    from utils.llm import ask, web_search_tool

    system_prompt = (
        "Sos un analista que hace un chequeo rápido de novedades corporativas. "
        "Respondé en UNA sola línea: si encontraste algo estructural relevante "
        "(cambio de CEO/CFO, M&A, evento regulatorio grave) desde la fecha dada, "
        "empezá con '🚩 ' y describilo brevemente. Si no encontraste nada relevante, "
        "respondé exactamente: 'Sin novedades estructurales.'"
    )
    user_prompt = (
        f"Compañía: {company} (ticker: {ticker}). "
        f"Buscá novedades corporativas estructurales desde el {fecha_ultima_corrida}."
    )
    try:
        return ask(system_prompt, user_prompt, tools=web_search_tool(max_uses=2), max_tokens=200)
    except Exception as e:
        return f"(chequeo profundo falló: {e})"


def check_triggers(
    price_threshold_pct: float = 20.0,
    days_threshold: int = 95,
    deep: bool = False,
) -> list[dict]:
    """Delta Detector: revisa todas las empresas con historial registrado y
    señala cuáles conviene refrescar. NO corre el pipeline de agentes — es
    un chequeo barato (yfinance, sin tokens) pensado para correr seguido.

    Retorna la lista de resultados por empresa (para uso programático /
    testing); además imprime una tabla legible en consola.
    """
    latest = history_db.get_latest_per_company()
    if not latest:
        console.print(
            "[yellow]No hay corridas registradas todavía en el historial. "
            "Corré al menos un --mode full para alguna empresa primero.[/yellow]"
        )
        return []

    console.print(Panel(
        f"[bold cyan]Delta Detector[/bold cyan]  [dim](umbral de precio: ±{price_threshold_pct:.0f}%, "
        f"umbral de días: {days_threshold})[/dim]",
        border_style="cyan",
    ))

    resultados = []
    for row in latest:
        company = row["company"]
        ticker = row["ticker"]
        precio_anterior = row["precio_referencia"]
        fecha_anterior = row["fecha"] or row["created_at"][:10]

        dias_transcurridos = (
            datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])
        ).days

        if not ticker:
            console.print(f"  [dim]{company}: sin ticker registrado, no se puede chequear precio.[/dim]")
            resultados.append({"company": company, "trigger": False, "motivo": "sin ticker"})
            continue

        precio_actual = _get_current_price(ticker)
        pct_change = None
        price_trigger = False
        if precio_actual is not None and precio_anterior:
            pct_change = (precio_actual / precio_anterior - 1) * 100
            price_trigger = abs(pct_change) >= price_threshold_pct

        time_trigger = dias_transcurridos >= days_threshold

        motivos = []
        if price_trigger:
            motivos.append(f"precio movió {pct_change:+.1f}% (umbral ±{price_threshold_pct:.0f}%)")
        if time_trigger:
            motivos.append(f"{dias_transcurridos} días desde la última corrida (umbral {days_threshold})")

        deep_flag = None
        if deep and (price_trigger or time_trigger):
            deep_flag = _deep_structural_check(company, ticker, fecha_anterior)
            if deep_flag and deep_flag.startswith("🚩"):
                motivos.append(deep_flag)

        trigger = bool(motivos)
        color = "yellow" if trigger else "green"
        precio_str = f"${precio_actual:.2f}" if precio_actual is not None else "N/D"
        estado = "🔔 REVISAR" if trigger else "✓ sin novedad"
        console.print(
            f"  [{color}]{estado}[/{color}]  {company} ({ticker}) — precio registrado ${precio_anterior:.2f} → "
            f"actual {precio_str}  |  {'; '.join(motivos) if motivos else 'sin triggers'}"
        )

        resultados.append({
            "company": company, "ticker": ticker, "precio_anterior": precio_anterior,
            "precio_actual": precio_actual, "pct_change": pct_change,
            "dias_transcurridos": dias_transcurridos, "trigger": trigger, "motivos": motivos,
        })

    n_triggers = sum(1 for r in resultados if r["trigger"])
    console.print(f"\n[bold]{n_triggers} de {len(resultados)} empresas necesitan revisión.[/bold]")
    if n_triggers:
        console.print("[dim]Corré: python main.py \"<empresa>\" --mode lite  para cada una marcada arriba.[/dim]")

    return resultados


def main():
    parser = argparse.ArgumentParser(
        description="Agentes-AF: Análisis de inversión multi-agente",
    )
    parser.add_argument(
        "company",
        nargs="?",
        default=None,
        help="Nombre de la compañía a analizar (ej: 'Apple', 'Mercado Libre', 'Costco'). No hace falta con --check-triggers.",
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
        help="Forzar corrida limpia: borra reportes existentes de la empresa antes de arrancar (solo --mode full)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "lite"],
        default="full",
        help=(
            "full (default): pipeline completo, los 10 agentes. "
            "lite: refresh trimestral — solo recalcula datos financieros, métricas y "
            "valoración (Agentes 4/7/8); requiere una corrida --mode full previa."
        ),
    )

    parser.add_argument(
        "--pabrai-xlsx",
        default=None,
        help=(
            "Path al Excel del checklist Pabrai (ej: checklist_pabrai.xlsx). "
            "Si se pasa, corre el Agente 11 al final del pipeline (full o lite). "
            "Si se omite, el Agente 11 no corre."
        ),
    )
    parser.add_argument(
        "--pabrai-sheet",
        default=None,
        help="Nombre de hoja a usar/crear en el Excel del checklist (default: mismo nombre que 'company').",
    )

    parser.add_argument(
        "--check-triggers",
        action="store_true",
        help=(
            "Delta Detector: no analiza una empresa — revisa todas las empresas con "
            "historial registrado (precio actual vía yfinance, sin tokens de LLM) y "
            "señala cuáles conviene refrescar. Ignora el argumento 'company'."
        ),
    )
    parser.add_argument(
        "--price-threshold-pct",
        type=float,
        default=20.0,
        help="Umbral de movimiento de precio (%%) para marcar una empresa como 'revisar' en --check-triggers (default: 20).",
    )
    parser.add_argument(
        "--days-threshold",
        type=int,
        default=95,
        help="Días desde la última corrida para marcar una empresa como 'revisar' en --check-triggers (default: 95, ~1 trimestre).",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help=(
            "Solo con --check-triggers: además del chequeo de precio/tiempo (gratis), hace "
            "una búsqueda web barata por empresa marcada para detectar cambios estructurales "
            "(CEO, M&A). Cuesta ~$0.01-0.03 por empresa marcada."
        ),
    )

    args = parser.parse_args()

    if args.check_triggers:
        check_triggers(
            price_threshold_pct=args.price_threshold_pct,
            days_threshold=args.days_threshold,
            deep=args.deep,
        )
        return

    if not args.company:
        parser.error("el argumento 'company' es obligatorio salvo que uses --check-triggers")

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

    hecho_nuevo = ""
    if args.mode == "lite":
        console.print("\n[bold cyan]─── Actualización trimestral ───[/bold cyan]")
        hecho_nuevo = console.input(
            "[yellow]¿Pegás los resultados del último trimestre / hechos relevantes? "
            "(Enter para que el agente los busque solo vía web search): [/yellow]"
        ).strip()

    output_dir = None if args.no_save else args.output
    run_analysis(
        args.company,
        precio_actual,
        fecha_precio,
        notas_corporativas,
        output_dir,
        fresh=args.fresh,
        mode=args.mode,
        hecho_nuevo=hecho_nuevo,
        pabrai_xlsx=args.pabrai_xlsx,
        pabrai_sheet=args.pabrai_sheet,
    )


if __name__ == "__main__":
    main()
