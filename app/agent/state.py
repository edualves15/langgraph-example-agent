from langgraph.prebuilt.chat_agent_executor import AgentState as ReActAgentState


class AgentState(ReActAgentState):
    """Estado **genérico** do agente (sem domínio).

    Herda `messages` (reducer oficial `add_messages`) e `remaining_steps` do estado
    padrão do `create_react_agent`.

    `tools` recebe as ferramentas de **frontend** anunciadas pelo cliente em runtime
    (campo `tools` do `RunAgentInput`). A integração oficial `ag_ui_langgraph` escreve
    essa lista em `state["tools"]`; declará-la aqui é o que a torna **legível** pelo nó
    do agente, que então as vincula ao LLM (sem executá-las — a execução acontece no
    navegador). Ver `app/agent/graph.py`.

    As chaves de **estado compartilhado do domínio** NÃO vivem aqui — cada domínio
    estende este schema com as suas (ex.: `reservation`/`delivery`). Ver o contrato
    `Domain.state_schema` em `app/agent/domain.py` e `app/domain/restaurant/state.py`.
    """

    tools: list[dict]
