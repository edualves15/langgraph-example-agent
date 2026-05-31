from langchain_core.messages import ToolMessage
from langgraph.graph import END

from app.agent.state import AgentState
from app.config import settings


def route_after_agent(state: AgentState):
    last = state["messages"][-1]
    if not getattr(last, "tool_calls", None):
        return END
    tool_calls_used = sum(
        1 for m in state["messages"] if isinstance(m, ToolMessage))
    if tool_calls_used >= settings.max_tool_calls:
        return END
    return "tools"
