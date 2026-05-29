from typing import Literal

from app.agent.state import AgentState
from app.config import settings


def route_after_agent(state: AgentState) -> Literal["tools", "end"]:
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None)

    if tool_calls and state.get("tool_calls_count", 0) < settings.max_tool_calls:
        return "tools"

    return "end"
