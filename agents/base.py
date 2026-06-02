"""Clase base para todos los agentes de análisis."""

from __future__ import annotations

from utils.llm import ask


class BaseAgent:
    """Clase base que define la interfaz común de todos los agentes."""

    name: str = "BaseAgent"
    description: str = ""
    system_prompt: str = ""
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8192

    def build_user_prompt(self, company: str) -> str:
        """Construye el prompt de usuario con el nombre de la compañía."""
        return f"Compañía a analizar: **{company}**\n"

    def build_cached_context(self, context: dict[str, str] | None) -> str | None:
        """Serializa el contexto acumulado de agentes previos para enviarlo cacheado."""
        if not context:
            return None
        parts = ["=== Contexto de agentes previos ==="]
        for agent_name, output in context.items():
            parts.append(f"\n--- {agent_name} ---\n{output}")
        parts.append("\n=== Fin del contexto ===\n")
        return "\n".join(parts)

    def run(self, company: str, context: dict[str, str] | None = None) -> str:
        """Ejecuta el agente y retorna su análisis como texto."""
        user_prompt = self.build_user_prompt(company)
        cached_context = self.build_cached_context(context)
        return ask(
            self.system_prompt,
            user_prompt,
            model=self.model,
            max_tokens=self.max_tokens,
            cached_context=cached_context,
        )
