"""Clase base para todos los agentes de análisis."""

from __future__ import annotations

from utils.llm import ask


class BaseAgent:
    """Clase base que define la interfaz común de todos los agentes."""

    name: str = "BaseAgent"
    description: str = ""
    system_prompt: str = ""
    max_tokens: int = 8192

    def build_user_prompt(self, company: str, context: dict[str, str] | None = None) -> str:
        """Construye el prompt de usuario con el nombre de la compañía y contexto previo."""
        parts = [f"Compañía a analizar: **{company}**\n"]
        if context:
            parts.append("=== Contexto de agentes previos ===")
            for agent_name, output in context.items():
                parts.append(f"\n--- {agent_name} ---\n{output}")
            parts.append("\n=== Fin del contexto ===\n")
        return "\n".join(parts)

    def run(self, company: str, context: dict[str, str] | None = None) -> str:
        """Ejecuta el agente y retorna su análisis como texto."""
        user_prompt = self.build_user_prompt(company, context)
        return ask(self.system_prompt, user_prompt, max_tokens=self.max_tokens)
