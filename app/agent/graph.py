from langgraph.graph import END, START, StateGraph

from app.agent.edges import route_after_agent
from app.agent.nodes import build_agent_node, build_tool_node
from app.agent.state import AgentState
from app.registries.mcp_registry import get_mcp_tools
from app.registries.tool_registry import get_local_tools
from app.services.llm_service import get_llm


async def build_graph():
    tools = get_local_tools() + await get_mcp_tools()
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", build_agent_node(llm_with_tools))
    graph.add_node("tools", build_tool_node(tools))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {"tools": "tools", "end": END},
    )
    graph.add_edge("tools", "agent")

    return graph.compile()
