"""
Schema de eventos canonicos para narracao agente→front-end.

Framework-agnostic — nao importa langgraph, langchain, nem qualquer
framework de agente. Dataclasses puras, serializaveis para JSON/NDJSON.

Alinhado com:
- AG-UI Protocol (event types e lifecycle start→delta→stop)
- OpenAI Responses API (eventos semanticos)
- Anthropic streaming (content blocks com indices estaveis)
- agent-event-protocol (stage lifecycle)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Tipos canonicos
# ---------------------------------------------------------------------------

EventType = Literal[
    "run_started",
    "run_finished",
    "step_started",
    "step_finished",
    "block_start",
    "block_delta",
    "block_stop",
    "tool_call",
    "tool_result",
    "text_delta",
    "reasoning_delta",
    "error",
]

Stage = Literal["start", "delta", "stop"]

Level = Literal[1, 2, 3]
"""Progressive disclosure:
1 = resumo (notificacao)
2 = detalhe normal
3 = tecnico / verbose
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def new_block_id() -> str:
    """Gera um block_id curto e estavel (12 chars hex)."""
    return uuid.uuid4().hex[:12]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# NarrationEvent
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NarrationEvent:
    """Evento canonico de narracao.

    Attributes:
        type: Tipo semantico do evento (step_started, tool_call, etc.).
        stage: Fase do ciclo de vida (start, delta, stop).
        block_id: Identificador estavel para correlacao front-end.
        text: Texto descritivo para renderizacao.
        tool_name: Nome da ferramenta (apenas eventos de tool).
        tool_call_id: ID da tool call do LLM (apenas eventos de tool).
        icon: Emoji ou string de icone para UI.
        level: Nivel de progressive disclosure (1-3).
        error: Mensagem de erro (apenas eventos error).
        duration_ms: Duracao em milissegundos (opcional, stage=stop).
        data: Payload adicional (args, output, etc.).
    """

    type: EventType
    stage: Stage
    block_id: str = field(default_factory=new_block_id)

    # Display
    text: str = ""
    icon: str = ""

    # Tool-specific
    tool_name: str = ""
    tool_call_id: str = ""

    # Metadata
    level: Level = 2
    timestamp: str = field(default_factory=_utc_now)

    # Optional enrichments
    error: str = ""
    duration_ms: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict pronto para JSON/NDJSON."""
        d: dict[str, Any] = {
            "type": self.type,
            "stage": self.stage,
            "blockId": self.block_id,
            "level": self.level,
            "timestamp": self.timestamp,
        }
        if self.text:
            d["text"] = self.text
        if self.icon:
            d["icon"] = self.icon
        if self.tool_name:
            d["toolName"] = self.tool_name
        if self.tool_call_id:
            d["toolCallId"] = self.tool_call_id
        if self.error:
            d["error"] = self.error
        if self.duration_ms:
            d["durationMs"] = self.duration_ms
        if self.data:
            d["data"] = self.data
        return d
