from langgraph.prebuilt.chat_agent_executor import AgentState as ReActAgentState


class AgentState(ReActAgentState):
    """Estado **genérico** do agente (sem domínio). Herda `messages` (`add_messages`) e
    `remaining_steps` do `create_react_agent`.

    `tools` são as ferramentas de **frontend** anunciadas pelo cliente em runtime
    (`RunAgentInput.tools`); a lib `ag_ui_langgraph` as escreve em `state["tools"]` e
    declará-las aqui as torna legíveis pelo nó `agent` (que as vincula ao LLM, sem executá-las
    — a execução é no navegador). Ver `app/agent/graph.py`.

    As chaves de estado do **domínio** NÃO vivem aqui — cada domínio estende este schema
    (ex.: `RestaurantState` com `reservation`/`delivery`). Ver `app/agent/domain.py`.
    """

    tools: list[dict]
