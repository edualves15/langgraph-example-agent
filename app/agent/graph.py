from langgraph.graph import END, START, StateGraph

from app.agent.edges import should_continue
from app.agent.nodes import build_agent_node, build_tool_node
from app.agent.state import AgentState
from app.registries.tool_registry import get_local_tools
from app.services.llm_service import get_llm


async def build_graph():
    tools = get_local_tools()
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = get_llm().bind_tools(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", build_agent_node(llm_with_tools, tools_by_name))
    graph.add_node("tools", build_tool_node(tools_by_name))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile(), tools
