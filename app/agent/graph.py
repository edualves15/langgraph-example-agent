from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import RetryPolicy

from app.agent.edges import route_after_agent
from app.agent.nodes import build_agent_node
from app.agent.state import AgentState
from app.mcp.client import load_mcp_tools
from app.registries.tool_registry import get_local_tools
from app.services.llm_service import get_llm


async def build_graph():
    tools = get_local_tools() + await load_mcp_tools()
    llm_with_tools = get_llm().bind_tools(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", build_agent_node(llm_with_tools))
    graph.add_node("tools", ToolNode(
        tools, handle_tool_errors=lambda e: f"Erro: {e}"), retry=RetryPolicy(max_attempts=3))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, ["tools", END])
    graph.add_edge("tools", "agent")

    return graph.compile(), tools
