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

    `reservation` e `delivery` são **estado compartilhado** (agente-owned) do domínio: os
    dois fluxos possíveis, com a MESMA forma padronizada — um objeto
    `{ items: [{name, price}], ...campos }` — e apenas o do fluxo ATIVO fica preenchido (o
    outro permanece `{}`):

    - `reservation` = `{ items, date, time, party_size, customer_name }` (reserva de mesa);
    - `delivery`    = `{ items, customer_name, address, phone, notes }` (pedido p/ delivery).

    Uma tool os muta retornando `Command(update={...})` e a lib emite
    `STATE_SNAPSHOT`/`STATE_DELTA` automaticamente; o front os renderiza genericamente. Ver
    `update_reservation` / `update_delivery` em `app/tools/restaurant_tools.py`.
    """

    tools: list[dict]
    reservation: dict
    delivery: dict
