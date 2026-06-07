"""Contrato `Domain` — o plug de negócio injetado no engine genérico.

O engine (`app/agent/graph.py`) é agnóstico de domínio: recebe um `Domain` e nunca importa
o negócio. Trocar de domínio = montar outro `Domain` no composition root (`app/main.py`).
"""

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class Domain:
    name: str                                          # identificador (logs)
    tools: list[BaseTool]                              # tools de backend do domínio
    state_schema: type                                 # subclasse de AgentState (chaves do domínio)
    prompt: str                                        # fragmento de system prompt (papel/fluxos)
    predict_state: list[dict] = field(default_factory=list)  # mapeamento AG-UI PredictState
    ui_hints: dict = field(default_factory=dict)       # {state_tag_icons, state_titles} p/ o front
