import logging
from collections.abc import AsyncIterator
from typing import NoReturn

from langchain_core.messages import HumanMessage

from app.agent.graph import build_graph
from app.exceptions import AgentError, AgentRuntimeError, ProviderAuthError, QuotaExceededError
from app.narration import NarrationAdapter
from app.narration.events import NarrationEvent

logger = logging.getLogger(__name__)


def _http_status(exc: BaseException) -> int | None:
    current: BaseException | None = exc
    while current is not None:
        for attr in ("status_code", "code", "status"):
            val = getattr(current, attr, None)
            if isinstance(val, int) and 400 <= val < 600:
                return val
        current = current.__cause__ or current.__context__
    return None


def _classify_error(exc: BaseException) -> tuple[str, str]:
    status = _http_status(exc)
    if status == 429:
        return "quota_exceeded", "Cota da API excedida. Tente novamente em breve."
    if status in (401, 403):
        return "auth_error", "Erro de configuração do serviço."
    return "runtime_error", "Erro interno ao processar a mensagem."


def _raise_classified(exc: Exception) -> NoReturn:
    status = _http_status(exc)
    if status == 429:
        raise QuotaExceededError() from exc
    if status in (401, 403):
        raise ProviderAuthError() from exc
    raise AgentRuntimeError() from exc


def _extract_content(content) -> str:
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _narration_event_to_sse(event: NarrationEvent) -> dict | None:
    """Converte NarrationEvent para payload SSE. Retorna None para eventos silenciosos."""
    etype = event.type
    if etype == "tool_call" and event.stage == "start":
        return {
            "_event": "step",
            "status": "running",
            "text": event.text,
            "icon": event.icon,
            "tool_name": event.tool_name,
            "block_id": event.block_id,
        }
    if etype == "tool_result":
        return {
            "_event": "step",
            "status": "done",
            "text": event.text,
            "icon": event.icon,
            "tool_name": event.tool_name,
            "duration_ms": event.duration_ms,
        }
    if etype == "error":
        return {
            "_event": "step",
            "status": "error",
            "text": event.text,
            "icon": event.icon,
            "tool_name": event.tool_name,
            "error": event.error,
        }
    if etype == "reasoning_started":
        return {
            "_event": "step",
            "status": "thinking",
            "text": event.text,
            "icon": event.icon,
        }
    return None


class AgentService:
    def __init__(self):
        self._graph = None
        self._tools: list = []

    async def warmup(self) -> None:
        await self._get_graph()

    async def _get_graph(self):
        if self._graph is None:
            self._graph, self._tools = await build_graph()
            logger.info(
                "Grafo do agente inicializado com %d ferramenta(s): %s",
                len(self._tools),
                ", ".join(t.name for t in self._tools),
            )
        return self._graph

    def _initial_state(self, message: str) -> dict:
        return {"messages": [HumanMessage(content=message)]}

    async def run(self, message: str) -> str:
        try:
            graph = await self._get_graph()
            final_state = await graph.ainvoke(self._initial_state(message))
        except AgentError:
            raise
        except Exception as exc:
            logger.exception("Erro durante invocação do agente")
            _raise_classified(exc)
        messages = final_state.get("messages", [])
        if not messages:
            logger.error("Grafo retornou estado sem mensagens")
            raise AgentRuntimeError()
        return _extract_content(messages[-1].content)

    async def stream(self, message: str) -> AsyncIterator[dict]:
        try:
            graph = await self._get_graph()
        except Exception as exc:
            logger.exception("Falha ao inicializar o grafo do agente")
            error_key, detail = _classify_error(exc)
            yield {"_event": "error", "error": error_key, "detail": detail}
            return

        answer_buffer: list[str] = []
        try:
            async for item in NarrationAdapter(
                graph.astream_events(self._initial_state(message), version="v2")
            ):
                if isinstance(item, str):
                    answer_buffer.append(item)
                elif isinstance(item, NarrationEvent):
                    if item.type == "run_finished":
                        break
                    payload = _narration_event_to_sse(item)
                    if payload is not None:
                        yield payload
        except Exception as exc:
            logger.exception("Erro durante stream do agente")
            error_key, detail = _classify_error(exc)
            yield {"_event": "error", "error": error_key, "detail": detail}
            return

        answer = "".join(answer_buffer).strip()
        if answer:
            yield {"_event": "done", "answer": answer}
        else:
            logger.warning("[agent] stream concluído sem resposta de texto para: %.80s", message)
            yield {
                "_event": "done",
                "answer": (
                    "Não foi possível gerar uma resposta. "
                    "Tente reformular a pergunta."
                ),
            }
