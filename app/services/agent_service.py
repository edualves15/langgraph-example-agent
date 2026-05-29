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


def _process_step(node: str, update: dict, tool_map: dict) -> str | None:
    """Loga o passo do grafo e retorna texto SSE (ou None se não for exibível)."""
    messages = update.get("messages", [])
    if node == "agent":
        last = messages[-1] if messages else None
        if isinstance(last, AIMessage) and last.tool_calls:
            names = ", ".join(tc["name"] for tc in last.tool_calls)
            logger.info("[agent] chamando tools: %s", names)
            parts = []
            for tc in last.tool_calls:
                tool = tool_map.get(tc["name"])
                template = tool.metadata.get(
                    "step_label", tc["name"]) if tool else tc["name"]
                try:
                    parts.append(template.format(**tc.get("args", {})))
                except (KeyError, IndexError):
                    parts.append(template)
            return " | ".join(parts) + "..."
        logger.info("[agent] resposta final gerada")
        return "Gerando resposta..."
    if node == "tools":
        for msg in messages:
            if isinstance(msg, ToolMessage):
                logger.info("[tools] %s → %s", msg.name, msg.content)
        return "Verificado. Gerando resposta..."
    if node == "increment":
        logger.info("[increment] tool_calls_count=%s",
                    update.get("tool_calls_count"))
    return None


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
                    text = _process_step(node_name, update, self._tool_map)
                    if text:
                        yield {"text": text}
                    if node_name == "agent":
                        last_agent_messages = update.get("messages", [])
        except Exception as exc:
            status = _http_status(exc)
            if status == 429:
                yield {"error": "quota_exceeded", "detail": "Cota da API excedida. Tente novamente em breve."}
            elif status in (401, 403):
                yield {"error": "auth_error", "detail": "Erro de configuração do serviço."}
            else:
                yield {"error": "runtime_error", "detail": "Erro interno ao processar a mensagem."}
            return
        if last_agent_messages:
            yield {"answer": _extract_content(last_agent_messages[-1].content)}
