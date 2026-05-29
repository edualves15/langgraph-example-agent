from langgraph.graph import END
from langgraph.types import Send

from app.agent.state import AgentState
from app.config import settings


def route_after_agent(state: AgentState):
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None)
    if tool_calls and state.get("tool_calls_count", 0) < settings.max_tool_calls:
        return [Send("execute_tool", {**state, "tool_call": tc}) for tc in tool_calls]
    return END
