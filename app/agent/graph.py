from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.agent.edges import route_after_agent
from app.agent.nodes import build_agent_node, build_execute_tool_node, increment_tool_count
from app.agent.state import AgentState
from app.mcp.client import load_mcp_tools
from app.registries.tool_registry import get_local_tools
from app.services.llm_service import get_llm


async def build_graph():
    tools = get_local_tools() + await load_mcp_tools()
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", build_agent_node(llm_with_tools))
    graph.add_node("execute_tool", build_execute_tool_node(
        tools), retry=RetryPolicy(max_attempts=3))
    graph.add_node("increment", increment_tool_count)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent", route_after_agent, ["execute_tool", END])
    graph.add_edge("execute_tool", "increment")
    graph.add_edge("increment", "agent")

    return graph.compile(), tools
