import logging
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import build_graph
from app.exceptions import AgentRuntimeError, ProviderAuthError, QuotaExceededError

logger = logging.getLogger(__name__)

_STREAM_ERRORS: dict[int, tuple[str, str]] = {
    429: ("quota_exceeded", "Cota da API excedida. Tente novamente em breve."),
    401: ("auth_error", "Erro de configuração do serviço."),
    403: ("auth_error", "Erro de configuração do serviço."),
}


def _http_status(exc: BaseException) -> int | None:
    current: BaseException | None = exc
    while current is not None:
        for attr in ("status_code", "code", "status"):
            val = getattr(current, attr, None)
            if isinstance(val, int) and 400 <= val < 600:
                return val
        current = current.__cause__ or current.__context__
    return None


def _extract_content(content) -> str:
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content


def _meta_fields(meta: dict) -> dict:
    return {k: meta[src] for k, src in (("icon", "step_icon"), ("category", "step_category")) if src in meta}


def _process_step(node: str, update: dict, tool_map: dict) -> list[tuple[str, dict]]:
    messages = update.get("messages", [])

    if node == "agent":
        last = messages[-1] if messages else None
        if isinstance(last, AIMessage) and last.tool_calls:
            logger.info("[agent] chamando tools: %s", ", ".join(
                tc["name"] for tc in last.tool_calls))
            events = []
            for tc in last.tool_calls:
                meta = getattr(tool_map.get(tc["name"]), "metadata", {})
                template = meta.get("step_label", tc["name"])
                try:
                    text = template.format(**tc.get("args", {}))
                except (KeyError, IndexError):
                    text = template
                events.append(
                    ("step", {"text": f"{text}...", **_meta_fields(meta)}))
            return events
        logger.info("[agent] resposta final gerada")
        return [("step", {"text": "Gerando resposta...", "icon": "thinking", "category": "agent"})]

    if node == "tools":
        events = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                logger.info("[tools] %s → %s", msg.name, msg.content)
                meta = getattr(tool_map.get(msg.name), "metadata", {})
                events.append(
                    ("tool_result", {"tool": msg.name, "result": msg.content, **_meta_fields(meta)}))
        return events

    if node == "increment":
        logger.info("[increment] tool_calls_count=%s",
                    update.get("tool_calls_count"))
    return []


class AgentService:
    def __init__(self):
        self._graph = None
        self._tool_map: dict = {}

    async def warmup(self) -> None:
        await self._get_graph()

    async def _get_graph(self):
        if self._graph is None:
            self._graph, tools = await build_graph()
            self._tool_map = {t.name: t for t in tools}
        return self._graph

    def _initial_state(self, message: str) -> dict:
        return {"messages": [HumanMessage(content=message)], "tool_calls_count": 0}

    async def run(self, message: str) -> str:
        graph = await self._get_graph()
        try:
            final_state = await graph.ainvoke(self._initial_state(message))
        except Exception as exc:
            status = _http_status(exc)
            if status == 429:
                raise QuotaExceededError() from exc
            if status in (401, 403):
                raise ProviderAuthError() from exc
            raise AgentRuntimeError() from exc
        messages = final_state.get("messages", [])
        if not messages:
            raise AgentRuntimeError()
        return _extract_content(messages[-1].content)

    async def stream(self, message: str) -> AsyncIterator[dict]:
        graph = await self._get_graph()
        last_agent_messages = None
        try:
            async for step in graph.astream(self._initial_state(message), stream_mode="updates"):
                for node_name, update in step.items():
                    for event_type, payload in _process_step(node_name, update, self._tool_map):
                        yield {"_event": event_type, **payload}
                    if node_name == "agent":
                        last_agent_messages = update.get("messages", [])
        except Exception as exc:
            key, detail = _STREAM_ERRORS.get(_http_status(
                exc), ("runtime_error", "Erro interno ao processar a mensagem."))
            yield {"_event": "error", "error": key, "detail": detail}
            return
        if last_agent_messages:
            yield {"_event": "done", "answer": _extract_content(last_agent_messages[-1].content)}
