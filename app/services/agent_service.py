import logging
from collections.abc import AsyncIterator
from typing import NoReturn

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import build_graph
from app.config import settings
from app.exceptions import AgentError, AgentRuntimeError, ProviderAuthError, QuotaExceededError

logger = logging.getLogger(__name__)


def _http_status(exc: BaseException) -> int | None:
    """Percorre a cadeia de causas buscando um HTTP status code."""
    current: BaseException | None = exc
    while current is not None:
        for attr in ("status_code", "code", "status"):
            val = getattr(current, attr, None)
            if isinstance(val, int) and 400 <= val < 600:
                return val
        current = current.__cause__ or current.__context__
    return None


def _classify_error(exc: BaseException) -> tuple[str, str]:
    """Retorna (error_key, detail_message) com base no HTTP status da exceção."""
    status = _http_status(exc)
    if status == 429:
        return "quota_exceeded", "Cota da API excedida. Tente novamente em breve."
    if status in (401, 403):
        return "auth_error", "Erro de configuração do serviço."
    return "runtime_error", "Erro interno ao processar a mensagem."


def _raise_classified(exc: Exception) -> NoReturn:
    """Re-levanta a exceção como erro de domínio classificado."""
    status = _http_status(exc)
    if status == 429:
        raise QuotaExceededError() from exc
    if status in (401, 403):
        raise ProviderAuthError() from exc
    raise AgentRuntimeError() from exc


def _extract_content(content) -> str:
    """Extrai texto da mensagem, suportando respostas multi-parte (Gemini)."""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _meta_fields(meta: dict) -> dict:
    return {k: meta[src] for k, src in (("icon", "step_icon"), ("category", "step_category")) if src in meta}


def _process_step(node: str, update: dict, tool_map: dict) -> list[tuple[str, dict]]:
    messages = update.get("messages", [])

    if node == "agent":
        last = messages[-1] if messages else None
        if isinstance(last, AIMessage) and last.tool_calls:
            tool_names = ", ".join(tc["name"] for tc in last.tool_calls)
            logger.info("[agent] solicitando %d ferramenta(s): %s",
                        len(last.tool_calls), tool_names)
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
        last_content = _extract_content(last.content) if last else ""
        logger.info("[agent] resposta final gerada (%d chars)",
                    len(last_content))
        return []

    if node == "tools":
        events = []
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            meta = getattr(tool_map.get(msg.name), "metadata", {})
            is_error = getattr(msg, "status", "success") == "error"
            if is_error:
                logger.warning("[tools] %s → erro | %s",
                               msg.name, str(msg.content)[:120])
                label = meta.get("step_error_label", f"{msg.name} falhou")
                events.append(
                    ("step", {"text": label, "icon": "error", "category": "error"}))
            else:
                content_str = str(msg.content)
                preview = content_str[:80] + \
                    "..." if len(content_str) > 80 else content_str
                logger.info("[tools] %s → ok | %s", msg.name, preview)
                label = meta.get("step_done_label", f"{msg.name} concluído")
                events.append(("step", {"text": label, **_meta_fields(meta)}))
        if events:
            events.append(
                ("step", {"text": "Gerando resposta...", "icon": "thinking", "category": "agent"}))
        return events

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
            logger.info(
                "Grafo do agente inicializado com %d ferramenta(s): %s",
                len(tools),
                ", ".join(t.name for t in tools),
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

        last_agent_messages = None
        tool_calls_done = 0
        try:
            async for step in graph.astream(self._initial_state(message), stream_mode="updates"):
                for node_name, update in step.items():
                    node_messages = update.get("messages", [])

                    if node_name == "agent":
                        last = node_messages[-1] if node_messages else None
                        # Ghost step fix: se já atingiu o limite, o route_after_agent
                        # vai para END sem executar as tools — não emitir os step events
                        if (
                            isinstance(last, AIMessage)
                            and last.tool_calls
                            and tool_calls_done >= settings.max_tool_calls
                        ):
                            logger.warning(
                                "[agent] limite de tool calls atingido (%d/%d); "
                                "descartando %d chamada(s) pendente(s)",
                                tool_calls_done,
                                settings.max_tool_calls,
                                len(last.tool_calls),
                            )
                            last_agent_messages = node_messages
                            continue

                    for event_type, payload in _process_step(node_name, update, self._tool_map):
                        yield {"_event": event_type, **payload}

                    if node_name == "tools":
                        tool_calls_done += sum(
                            1 for m in node_messages if isinstance(m, ToolMessage)
                        )
                    if node_name == "agent":
                        last_agent_messages = node_messages
        except Exception as exc:
            logger.exception("Erro durante stream do agente")
            error_key, detail = _classify_error(exc)
            yield {"_event": "error", "error": error_key, "detail": detail}
            return

        if last_agent_messages:
            last_msg = last_agent_messages[-1]
            content = _extract_content(last_msg.content)
            if content:
                yield {"_event": "done", "answer": content}
            else:
                # Empty answer fix: agente atingiu limite de tools sem gerar resposta final
                logger.warning(
                    "[agent] limite de tools atingido sem resposta final para: %.80s", message
                )
                yield {
                    "_event": "done",
                    "answer": (
                        "Não foi possível concluir a pesquisa dentro do limite de buscas. "
                        "Tente reformular a pergunta com mais detalhes ou de forma mais específica."
                    ),
                }
        else:
            logger.error(
                "Grafo concluído sem mensagem do agente para: %.80s", message)
            yield {"_event": "error", "error": "no_response", "detail": "Nenhuma resposta gerada pelo agente."}
