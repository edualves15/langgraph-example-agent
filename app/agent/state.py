from langgraph.prebuilt.chat_agent_executor import AgentState as ReActAgentState


class AgentState(ReActAgentState):
    """Estado do agente.

    Herda `messages` (reducer oficial `add_messages`) e `remaining_steps` do estado
    padrão do `create_react_agent`, e adiciona `proverbs` como estado compartilhado
    exposto à UI via eventos AG-UI `STATE_SNAPSHOT` / `STATE_DELTA`.
    """

    proverbs: list[str]
