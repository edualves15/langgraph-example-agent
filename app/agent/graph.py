from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import get_system_prompt
from app.agent.state import AgentState
from app.registries.tool_registry import get_local_tools
from app.services.llm_service import get_llm


def _prompt(state: AgentState) -> list:
    """Prompt dinâmico: injeta o system prompt (com a data de hoje) a cada chamada."""
    return [SystemMessage(content=get_system_prompt()), *state["messages"]]


def build_graph() -> CompiledStateGraph:
    """Constrói o grafo oficial (ReAct) compatível com a integração AG-UI.

    - `create_react_agent`: loop oficial agente↔ferramentas.
    - `state_schema=AgentState`: adiciona o estado compartilhado `proverbs`.
    - `checkpointer=MemorySaver`: persiste threads (requisito para human-in-the-loop).
    """
    return create_react_agent(
        model=get_llm(),
        tools=get_local_tools(),
        prompt=_prompt,
        state_schema=AgentState,
        checkpointer=MemorySaver(),
    )
