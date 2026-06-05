from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from app.agent.prompts import get_system_prompt
from app.agent.state import AgentState
from app.registries.tool_registry import get_local_tools
from app.services.llm_service import get_llm


def _prompt(state: AgentState) -> list:
    """Prompt dinâmico: injeta o system prompt (com a data de hoje) a cada chamada."""
    return [SystemMessage(content=get_system_prompt()), *state["messages"]]


def _frontend_tool_schemas(tools: list[dict], exclude: set[str]) -> list[dict]:
    """Converte as tools de frontend (AG-UI `{name, description, parameters}`) para o
    formato de tool que o `bind_tools` aceita. Ignora as que colidem com tools de
    backend (o backend vence) — assim o LLM nunca vê o mesmo nome duas vezes.
    """
    schemas: list[dict] = []
    for t in tools or []:
        name = t.get("name") if isinstance(t, dict) else None
        if not name or name in exclude:
            continue
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters")
                    or {"type": "object", "properties": {}},
                },
            }
        )
    return schemas


def build_graph() -> CompiledStateGraph:
    """Constrói o grafo (loop ReAct) compatível com a integração AG-UI.

    Diferente do prebuilt `create_react_agent` (cujo `ToolNode` executa **toda** tool
    call), este grafo distingue tools de **backend** (executadas no servidor) de tools
    de **frontend** (anunciadas pelo cliente em runtime via `RunAgentInput.tools`, que a
    lib `ag_ui_langgraph` escreve em `state["tools"]`):

    - o nó `agent` vincula ao LLM **as tools de backend + os schemas das tools de
      frontend**, então o modelo pode chamar qualquer uma;
    - o roteamento executa no servidor apenas chamadas a tools de backend; uma chamada a
      tool de frontend **encerra o run** (`END`) — a lib já emitiu `TOOL_CALL_*` a partir
      da AIMessage, e o navegador executa a ação e retoma enviando um `ToolMessage` no
      próximo run (ver `web/app.js` / `web/frontend-tools.js`).

    `state_schema=AgentState` declara `tools` (legível pelo nó). `checkpointer` persiste
    threads (requisito para human-in-the-loop, ex.: `create_reservation`).
    """
    model = get_llm()
    backend_tools = get_local_tools()
    backend_names = {t.name for t in backend_tools}

    async def agent_node(state: AgentState) -> dict:
        frontend = _frontend_tool_schemas(state.get("tools") or [], exclude=backend_names)
        model_with_tools = model.bind_tools([*backend_tools, *frontend])
        response = await model_with_tools.ainvoke(_prompt(state))
        return {"messages": [response]}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None)
        if not tool_calls:
            return END
        # Executa no servidor só quando TODA chamada é de uma tool de backend.
        # Qualquer chamada a uma tool de frontend devolve o controle ao navegador.
        if all(tc["name"] in backend_names for tc in tool_calls):
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(backend_tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=MemorySaver())
