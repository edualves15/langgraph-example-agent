import logging
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import build_graph
from app.exceptions import AgentRuntimeError, ProviderAuthError, QuotaExceededError

logger = logging.getLogger(__name__)


def _http_status(exc: BaseException) -> int | None:
    """Percorre a cadeia de exceções em busca de um status HTTP (provider-agnostic)."""
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
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return content


def _process_step(node: str, update: dict, tool_map: dict) -> list[tuple[str, dict]]:
    """Loga o passo do grafo e retorna lista de (event_type, payload) para SSE."""
    messages = update.get("messages", [])
    events: list[tuple[str, dict]] = []

    if node == "agent":
        last = messages[-1] if messages else None
        if isinstance(last, AIMessage) and last.tool_calls:
            names = ", ".join(tc["name"] for tc in last.tool_calls)
            logger.info("[agent] chamando tools: %s", names)
            for tc in last.tool_calls:
                tool = tool_map.get(tc["name"])
                meta = tool.metadata if tool else {}
                template = meta.get("step_label", tc["name"])
                try:
                    text = template.format(**tc.get("args", {}))
                except (KeyError, IndexError):
                    text = template
                payload: dict = {"text": text + "..."}
                if "step_icon" in meta:
                    payload["icon"] = meta["step_icon"]
                if "step_category" in meta:
                    payload["category"] = meta["step_category"]
                events.append(("step", payload))
        else:
            logger.info("[agent] resposta final gerada")
            events.append(
                ("step", {"text": "Gerando resposta...", "icon": "thinking", "category": "agent"}))

    elif node == "tools":
        for msg in messages:
            if isinstance(msg, ToolMessage):
                logger.info("[tools] %s → %s", msg.name, msg.content)
                tool = tool_map.get(msg.name)
                meta = tool.metadata if tool else {}
                payload = {"tool": msg.name, "result": msg.content}
                if "step_icon" in meta:
                    payload["icon"] = meta["step_icon"]
                if "step_category" in meta:
                    payload["category"] = meta["step_category"]
                events.append(("tool_result", payload))

    elif node == "increment":
        logger.info("[increment] tool_calls_count=%s",
                    update.get("tool_calls_count"))

    return events


class AgentService:
    def __init__(self):
        self._graph = None
        self._tool_map: dict = {}

    async def warmup(self) -> None:
        """Inicializa o grafo antecipadamente. Chame no startup da aplicação."""
        await self._get_graph()

    async def _get_graph(self):
        if self._graph is None:
            self._graph, tools = await build_graph()
            self._tool_map = {t.name: t for t in tools}
        return self._graph

    async def run(self, message: str) -> str:
        graph = await self._get_graph()
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "tool_calls_count": 0,
        }
        try:
            final_state = await graph.ainvoke(initial_state)
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
        """Executa o grafo e produz eventos de passo + resposta final para SSE."""
        graph = await self._get_graph()
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "tool_calls_count": 0,
        }
        last_agent_messages = None
        try:
            async for step in graph.astream(initial_state, stream_mode="updates"):
                for node_name, update in step.items():
                    for event_type, payload in _process_step(node_name, update, self._tool_map):
                        yield {"_event": event_type, **payload}
                    if node_name == "agent":
                        last_agent_messages = update.get("messages", [])
        except Exception as exc:
            status = _http_status(exc)
            if status == 429:
                yield {"_event": "error", "error": "quota_exceeded", "detail": "Cota da API excedida. Tente novamente em breve."}
            elif status in (401, 403):
                yield {"_event": "error", "error": "auth_error", "detail": "Erro de configuração do serviço."}
            else:
                yield {"_event": "error", "error": "runtime_error", "detail": "Erro interno ao processar a mensagem."}
            return
        if last_agent_messages:
            yield {"_event": "done", "answer": _extract_content(last_agent_messages[-1].content)}
