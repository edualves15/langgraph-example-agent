"""
Narration Engine — Camada de eventos canonicos para streaming agente→front-end.

Alinhado com o AG-UI Protocol (ag-ui-protocol/ag-ui) e com o padrao
content-block-centric (start → delta → stop) usado por Anthropic, OpenAI
e Vercel AI SDK.

Fornece:
- NarrationEvent: schema tipado de eventos (framework-agnostic)
- NarrationAdapter: tradutor raw LangGraph stream → NarrationEvent
- render_event(): consumer de terminal para desenvolvimento local
"""

from v2.narration.events import (
    EventType,
    Level,
    NarrationEvent,
    Stage,
    new_block_id,
)
from v2.narration.adapter import NarrationAdapter
from v2.narration.consumer import render_event

__all__ = [
    "EventType",
    "Level",
    "NarrationAdapter",
    "NarrationEvent",
    "Stage",
    "new_block_id",
    "render_event",
]
