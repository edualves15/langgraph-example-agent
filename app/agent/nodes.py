from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.config import settings


def build_agent_node(llm_with_tools):
    async def agent_node(state: AgentState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    return agent_node


def build_tool_node(tools):
    return ToolNode(tools)


def increment_tool_count(state: AgentState) -> dict:
    return {"tool_calls_count": state.get("tool_calls_count", 0) + 1}


def max_tool_calls_reached(state: AgentState) -> bool:
    return state.get("tool_calls_count", 0) >= settings.max_tool_calls
