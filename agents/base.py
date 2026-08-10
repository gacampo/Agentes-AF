"""Clase base para todos los agentes de análisis."""

from __future__ import annotations

from utils.llm import ask, web_search_tool


class BaseAgent:
    """Clase base que define la interfaz común de todos los agentes.

    Soporta dos modos de corrida:
    - "full": comportamiento original, analiza todo desde cero (o desde el
      contexto de los agentes previos). Es el default, no requiere cambios
      en los agentes que no lo necesiten.
    - "lite": modo refresh trimestral. Solo lo soportan los agentes que
      definen `system_prompt_lite` y sobreescriben `build_user_prompt_lite`.
      Recibe el output anterior del propio agente (la tesis/sección vigente)
      y actualiza solo lo que corresponde, sin re-narrar lo que no cambió.
    """

    name: str = "BaseAgent"
    description: str = ""
    system_prompt: str = ""
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8192

    # --- Web search en vivo (opt-in por agente) ---
    uses_web_search: bool = False
    web_search_max_uses: int = 6
    web_search_allowed_domains: list[str] | None = None

    # --- Modo lite (opt-in por agente) ---
    # Si un agente soporta refresh trimestral, define este system prompt
    # y sobreescribe build_user_prompt_lite(). Si queda en None, el agente
    # solo corre en modo full (comportamiento actual, sin cambios).
    system_prompt_lite: str | None = None

    def supports_lite(self) -> bool:
        return self.system_prompt_lite is not None

    def build_user_prompt(self, company: str) -> str:
        """Construye el prompt de usuario con el nombre de la compañía (modo full)."""
        return f"Compañía a analizar: **{company}**\n"

    def build_user_prompt_lite(
        self,
        company: str,
        previous_output: str,
        context: dict[str, str] | None = None,
    ) -> str:
        """Construye el prompt de usuario para modo lite (refresh).

        Los agentes que soportan lite DEBEN sobreescribir este método:
        típicamente arman el prompt a partir de `previous_output` (la
        salida anterior de este mismo agente) + lo que cambió, sin volver
        a investigar/redactar lo que sigue vigente.
        """
        raise NotImplementedError(
            f"{self.name} define system_prompt_lite pero no sobreescribió "
            "build_user_prompt_lite()."
        )

    def build_cached_context(self, context: dict[str, str] | None) -> str | None:
        """Serializa el contexto acumulado de agentes previos para enviarlo cacheado."""
        if not context:
            return None
        parts = ["=== Contexto de agentes previos ==="]
        for agent_name, output in context.items():
            parts.append(f"\n--- {agent_name} ---\n{output}")
        parts.append("\n=== Fin del contexto ===\n")
        return "\n".join(parts)

    def _tools(self) -> list[dict] | None:
        if not self.uses_web_search:
            return None
        return web_search_tool(
            max_uses=self.web_search_max_uses,
            allowed_domains=self.web_search_allowed_domains,
        )

    def run(
        self,
        company: str,
        context: dict[str, str] | None = None,
        mode: str = "full",
        previous_output: str | None = None,
    ) -> str:
        """Ejecuta el agente y retorna su análisis como texto.

        mode="full" (default): comportamiento original.
        mode="lite": requiere que el agente soporte lite (ver supports_lite())
        y que se le pase `previous_output` (la salida anterior de este agente,
        cargada del reporte vigente en disco).
        """
        if mode == "lite":
            if not self.supports_lite():
                raise ValueError(f"{self.name} no soporta modo lite (refresh).")
            if previous_output is None:
                raise ValueError(
                    f"{self.name} en modo lite requiere previous_output "
                    "(la salida anterior de este agente)."
                )
            system_prompt = self.system_prompt_lite
            user_prompt = self.build_user_prompt_lite(company, previous_output, context)
        elif mode == "full":
            system_prompt = self.system_prompt
            user_prompt = self.build_user_prompt(company)
        else:
            raise ValueError(f"mode debe ser 'full' o 'lite', recibido: {mode!r}")

        cached_context = self.build_cached_context(context)
        return ask(
            system_prompt,
            user_prompt,
            model=self.model,
            max_tokens=self.max_tokens,
            cached_context=cached_context,
            tools=self._tools(),
        )
