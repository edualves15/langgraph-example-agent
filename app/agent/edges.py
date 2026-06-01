import logging

from langchain_core.messages import ToolMessage
from langgraph.graph import END

from app.agent.state import AgentState
from app.config import settings

logger = logging.getLogger(__name__)


def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    if not messages:
        return END
    last = messages[-1]
    if not getattr(last, "tool_calls", None):
        return END
    tool_calls_used = sum(1 for m in messages if isinstance(m, ToolMessage))
    if tool_calls_used >= settings.max_tool_calls:
        logger.warning(
            "Limite de tool calls atingido (%d/%d) — encerrando ciclo",
            tool_calls_used,
            settings.max_tool_calls,
        )
        return END
    return "tools"
