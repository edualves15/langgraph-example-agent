from langchain_core.messages import HumanMessage

from app.agent.graph import build_graph


class AgentService:
    def __init__(self):
        self._graph = None

    async def warmup(self) -> None:
        """Inicializa o grafo antecipadamente. Chame no startup da aplicação."""
        await self._get_graph()

    async def _get_graph(self):
        if self._graph is None:
            self._graph = await build_graph()
        return self._graph

    async def run(self, message: str) -> str:
        graph = await self._get_graph()
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "tool_calls_count": 0,
        }
        final_state = await graph.ainvoke(initial_state)
        content = final_state["messages"][-1].content
        if isinstance(content, list):
            return "".join(block.get("text", "") for block in content if isinstance(block, dict))
        return content
