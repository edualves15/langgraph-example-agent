"""
Narration Engine — Camada de eventos canonicos para streaming agente→front-end.

Fornece:
- NarrationEvent: schema tipado de eventos (framework-agnostic)
- NarrationAdapter: tradutor raw LangGraph stream → NarrationEvent
- render_event(): consumer de terminal para desenvolvimento local
"""

from app.narration.events import (
    EventType,
    Level,
    NarrationEvent,
    Stage,
    new_block_id,
)
from app.narration.adapter import NarrationAdapter
from app.narration.consumer import render_event

__all__ = [
    "EventType",
    "Level",
    "NarrationAdapter",
    "NarrationEvent",
    "Stage",
    "new_block_id",
    "render_event",
]
