"""
NarrationAdapter — traduz astream_events(v2) do LangGraph em NarrationEvent.

Consome graph.astream_events(version="v2") e traduz cada evento LangChain/LangGraph
para NarrationEvent (eventos canonicos) ou str (tokens de texto em tempo real).

Uso:
    async for item in NarrationAdapter(graph.astream_events(state, version="v2")):
        if isinstance(item, NarrationEvent):
            render_event(item)
        elif isinstance(item, str):
            print(item, end="")  # streaming de tokens
"""

from __future__ import annotations

import time
from typing import AsyncIterator

from app.narration.events import NarrationEvent, new_block_id

# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class NarrationAdapter:
    """Async iterator que traduz eventos astream_events(v2) → NarrationEvent | str.

    Mapeamento:
        on_chat_model_start  → reasoning_started (tempo real!)
        on_chat_model_stream → str (token em tempo real)
        on_chat_model_end    → reasoning_end
        on_custom_event      → tool_call, tool_result, tool_error
    """

    def __init__(self, stream):
        self._stream = stream
        self._tool_timers: dict[str, float] = {}

    async def __aiter__(self) -> AsyncIterator[NarrationEvent | str]:
        async for event in self._stream:
            result = self._translate(event)
            if result is not None:
                yield result

        yield NarrationEvent(
            type="run_finished",
            stage="stop",
            block_id="run",
            level=1,
        )

    # ------------------------------------------------------------------
    # Translator
    # ------------------------------------------------------------------

    def _translate(self, event: dict) -> NarrationEvent | str | None:
        etype = event.get("event", "")
        name = event.get("name", "")
        data = event.get("data", {}) or {}

        # Ignora eventos de chain (nodes, grafo) — so nos interessam chat_model e custom
        if etype in ("on_chain_start", "on_chain_end"):
            return None

        # Chat model lifecycle → reasoning (TEMPO REAL)
        if etype == "on_chat_model_start":
            return self._handle_chat_model_start(data)
        elif etype == "on_chat_model_end":
            return self._handle_chat_model_end(data)
        elif etype == "on_chat_model_stream":
            return self._handle_chat_model_stream(data)

        # Custom events (adispatch_custom_event dos nos)
        if etype == "on_custom_event":
            return self._handle_custom(name, data)

        return None

    # ------------------------------------------------------------------
    # Chat model → reasoning (eventos em tempo real)
    # ------------------------------------------------------------------

    def _handle_chat_model_start(self, data: dict) -> NarrationEvent:
        return NarrationEvent(
            type="reasoning_started",
            stage="start",
            text=data.get("text", "Analisando..."),
            icon=data.get("icon", "💭"),
            level=1,
        )

    def _handle_chat_model_end(self, data: dict) -> NarrationEvent:
        return NarrationEvent(
            type="reasoning_end",
            stage="stop",
            level=1,
        )

    def _handle_chat_model_stream(self, data: dict) -> str | None:
        """Extrai token de texto do chunk do modelo."""
        chunk = data.get("chunk")
        if chunk is None:
            return None
        content = chunk.content if hasattr(chunk, "content") else chunk
        return _extract_text(content)

    # ------------------------------------------------------------------
    # Custom events (adispatch_custom_event)
    # ------------------------------------------------------------------

    def _handle_custom(self, name: str, data: dict) -> NarrationEvent | None:
        if name == "tool_call":
            return self._handle_tool_announce(data)
        elif name == "tool_result":
            return self._handle_tool_done(data)
        elif name == "tool_error":
            return self._handle_tool_error(data)
        return None

    def _handle_tool_announce(self, data: dict) -> NarrationEvent:
        tool_call_id = data.get("tool_call_id", "")
        if tool_call_id:
            self._tool_timers[tool_call_id] = time.time()
            block_id = tool_call_id
        else:
            block_id = new_block_id()

        return NarrationEvent(
            type="tool_call",
            stage="start",
            block_id=block_id,
            text=data.get("text", ""),
            icon=data.get("icon", ""),
            tool_name=data.get("tool_name", data.get("tool", "")),
            tool_call_id=tool_call_id,
            level=data.get("level", 2),
            data={"args": data.get("args", {})},
        )

    def _handle_tool_done(self, data: dict) -> NarrationEvent:
        tool_call_id = data.get("tool_call_id", data.get("tool", ""))
        start = self._tool_timers.pop(tool_call_id, None)
        duration = (time.time() - start) * 1000 if start else 0.0

        return NarrationEvent(
            type="tool_result",
            stage="stop",
            block_id=tool_call_id or new_block_id(),
            text=data.get("text", ""),
            icon=data.get("icon", ""),
            tool_name=data.get("tool", ""),
            tool_call_id=tool_call_id,
            duration_ms=round(duration, 1),
        )

    def _handle_tool_error(self, data: dict) -> NarrationEvent:
        tool_call_id = data.get("tool_call_id", data.get("tool", ""))
        start = self._tool_timers.pop(tool_call_id, None)
        duration = (time.time() - start) * 1000 if start else 0.0

        return NarrationEvent(
            type="error",
            stage="stop",
            block_id=tool_call_id or new_block_id(),
            text=data.get("text", ""),
            icon=data.get("icon", ""),
            tool_name=data.get("tool", ""),
            tool_call_id=tool_call_id,
            error=data.get("error", ""),
            duration_ms=round(duration, 1),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_text(content) -> str:
    """Extrai texto de conteudo de mensagem (string ou lista de blocos)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return ""
