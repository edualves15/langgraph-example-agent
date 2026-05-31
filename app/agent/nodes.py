from langchain_core.messages import SystemMessage

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState


def build_agent_node(llm_with_tools):
    async def agent_node(state: AgentState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    return agent_node


def build_execute_tool_node(tools: list):
    tool_map = {t.name: t for t in tools}

    async def execute_tool(state: ToolCallInput) -> dict:
        tc = state["tool_call"]
        tool = tool_map[tc["name"]]
        try:
            result = await tool.ainvoke(tc["args"])
        except Exception as exc:
            result = f"Erro: {exc}"
        return {"messages": [ToolMessage(content=str(result), tool_call_id=tc["id"], name=tc["name"])]}

    return execute_tool


def increment_tool_count(state: AgentState) -> dict:
    return {"tool_calls_count": state.get("tool_calls_count", 0) + 1}
