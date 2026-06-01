"""
NarrationAdapter — traduz stream raw do LangGraph em NarrationEvent canonicos.

Envolve graph.astream(stream_mode=["custom", "messages"]) e traduz cada
chunk para um NarrationEvent (eventos estruturados) ou str (tokens de texto).

Uso:
    async for event in NarrationAdapter(graph.astream(state, stream_mode=[...])):
        if isinstance(event, NarrationEvent):
            render_event(event)    # ou serializa para NDJSON/SSE
        elif isinstance(event, str):
            print(event, end="")  # streaming de tokens
"""

from __future__ import annotations

import time
from typing import AsyncIterator

from v2.narration.events import NarrationEvent, new_block_id

# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class NarrationAdapter:
    """Async iterator que traduz (mode, chunk) → NarrationEvent | str.

    Consome o stream dual-mode do LangGraph e emite:
    - NarrationEvent para eventos de status/tool
    - str para tokens de texto da resposta final

    Mantem estado interno para:
    - Gerar run_started / run_finished
    - Correlacionar tool calls por tool_call_id
    - Acumular duracoes
    """

    def __init__(self, stream):
        self._stream = stream
        self._started = False
        self._finished = False
        self._tool_timers: dict[str, float] = {}  # tool_call_id → start_time
        self._current_step_id = ""
        self._text_block_id = ""

    async def __aiter__(self) -> AsyncIterator[NarrationEvent | str]:
        async for mode, chunk in self._stream:
            result = self._translate(mode, chunk)
            if result is not None:
                yield result

        # Emite run_finished se ainda nao foi emitido
        if not self._finished:
            self._finished = True
            yield NarrationEvent(
                type="run_finished",
                stage="stop",
                block_id="run",
                level=1,
            )

    # ------------------------------------------------------------------
    # Translator
    # ------------------------------------------------------------------

    def _translate(self, mode: str, chunk) -> NarrationEvent | str | None:
        if mode == "custom":
            return self._handle_custom(chunk)
        elif mode == "messages":
            return self._handle_messages(chunk)
        return None

    # ------------------------------------------------------------------
    # Custom events (do StreamWriter nos nós)
    # ------------------------------------------------------------------

    def _handle_custom(self, chunk: dict) -> NarrationEvent | None:
        data = chunk if isinstance(chunk, dict) else {}

        # Suporte aos dois formatos: novo ("type": "narration") e legado ("type": "status", etc.)
        is_narration = data.get("type") == "narration"

        if is_narration:
            event_type = data.get("event", "")
            return self._handle_narration_event(event_type, data)

        # Fallback: formato legado (compatibilidade)
        legacy_type = data.get("type", "")
        if legacy_type == "status":
            return self._handle_step_started(data)
        elif legacy_type == "tool.start":
            return self._handle_tool_announce(data)
        elif legacy_type == "tool.done":
            return self._handle_tool_done(data)
        elif legacy_type == "tool.error":
            return self._handle_tool_error(data)

        return None

    def _handle_narration_event(self, event_type: str, data: dict) -> NarrationEvent | None:
        if event_type == "step_started":
            return self._handle_step_started(data)
        elif event_type == "tool_call":
            return self._handle_tool_announce(data)
        elif event_type == "tool_result":
            return self._handle_tool_done(data)
        elif event_type == "tool_error":
            return self._handle_tool_error(data)
        elif event_type == "reasoning_started":
            return self._handle_reasoning_started(data)
        elif event_type == "reasoning_stop":
            return self._handle_reasoning_stop(data)
        return None

    def _handle_reasoning_started(self, data: dict) -> NarrationEvent:
        return NarrationEvent(
            type="reasoning_started",
            stage="start",
            text=data.get("text", ""),
            level=data.get("level", 1),
        )

    def _handle_reasoning_stop(self, data: dict) -> NarrationEvent:
        return NarrationEvent(
            type="reasoning_stop",
            stage="stop",
            level=data.get("level", 1),
        )

    def _handle_step_started(self, data: dict) -> NarrationEvent:
        self._current_step_id = new_block_id()

        # Garante run_started antes do primeiro step
        if not self._started:
            self._started = True
            # Nao retornamos run_started aqui — o caller nao espera 2 eventos
            # Emitimos step_started diretamente; run_started e implicito

        return NarrationEvent(
            type="step_started",
            stage="start",
            block_id=self._current_step_id,
            text=data.get("text", ""),
            icon=data.get("icon", ""),
            level=data.get("level", 1),
        )

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

    # ------------------------------------------------------------------
    # Messages (streaming de tokens)
    # ------------------------------------------------------------------

    def _handle_messages(self, chunk) -> str | None:
        """Extrai tokens de texto do stream de mensagens."""
        token, meta = chunk
        # So transmite tokens do nó "agent" (resposta final), nao do tools
        if meta.get("langgraph_node") != "agent":
            return None

        content = token.content if hasattr(token, "content") else token
        return _extract_text(content)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_text(content) -> str:
    """Extrai texto de conteudo de mensagem (string ou lista de blocos)."""
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content) if content else ""
