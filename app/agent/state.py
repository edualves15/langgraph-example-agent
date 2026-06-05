from langgraph.prebuilt.chat_agent_executor import AgentState as ReActAgentState


class AgentState(ReActAgentState):
    """Estado do agente.

    Herda `messages` (reducer oficial `add_messages`) e `remaining_steps` do estado
    padrão do `create_react_agent`.

    `tools` recebe as ferramentas de **frontend** anunciadas pelo cliente em runtime
    (campo `tools` do `RunAgentInput`). A integração oficial `ag_ui_langgraph` escreve
    essa lista em `state["tools"]`; declará-la aqui é o que a torna **legível** pelo nó
    do agente, que então as vincula ao LLM (sem executá-las — a execução acontece no
    navegador). Ver `app/agent/graph.py`.
    """

    tools: list[dict]
