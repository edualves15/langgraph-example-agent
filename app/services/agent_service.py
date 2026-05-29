import logging

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


def _log_step(node: str, update: dict) -> None:
    """Loga de forma legível o que cada nó do grafo produziu."""
    messages = update.get("messages", [])
    if node == "agent":
        last = messages[-1] if messages else None
        if isinstance(last, AIMessage) and last.tool_calls:
            names = ", ".join(tc["name"] for tc in last.tool_calls)
            logger.info("[agent] chamando tools: %s", names)
        else:
            logger.info("[agent] resposta final gerada")
    elif node == "tools":
        for msg in messages:
            if isinstance(msg, ToolMessage):
                logger.info("[tools] %s → %s", msg.name, msg.content)
    elif node == "increment":
        logger.info("[increment] tool_calls_count=%s",
                    update.get("tool_calls_count"))


class AgentService:
    def __init__(self):
        self._graph = None

    async def warmup(self) -> None:
        """Inicializa o grafo antecipadamente. Chame no startup da aplicação."""
        await self._get_graph()

    async def _get_graph(self):
        if self._graph is None:
            self._graph = await build_graph()
        return self._graph

    async def run(self, message: str) -> str:
        graph = await self._get_graph()
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "tool_calls_count": 0,
        }
        try:
            last_agent_messages = None
            async for step in graph.astream(initial_state, stream_mode="updates"):
                for node_name, update in step.items():
                    _log_step(node_name, update)
                    if node_name == "agent":
                        last_agent_messages = update.get("messages", [])
        except Exception as exc:
            status = _http_status(exc)
            if status == 429:
                raise QuotaExceededError() from exc
            if status in (401, 403):
                raise ProviderAuthError() from exc
            raise AgentRuntimeError() from exc

        content = last_agent_messages[-1].content
        if isinstance(content, list):
            return "".join(block.get("text", "") for block in content if isinstance(block, dict))
        return content
