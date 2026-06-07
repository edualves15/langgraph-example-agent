from app.agent.state import AgentState


class RestaurantState(AgentState):
    """Estado do domínio **Restaurante** — estende o `AgentState` genérico com as chaves
    de **estado compartilhado** (agente-owned) do negócio.

    São os dois fluxos possíveis, com a MESMA forma padronizada — um objeto
    `{ items: [{name, price}], ...campos }` — e apenas o do fluxo ATIVO fica preenchido (o
    outro permanece `{}`):

    - `reservation` = `{ items, date, time, party_size, customer_name }` (reserva de mesa);
    - `delivery`    = `{ items, customer_name, address, phone, notes }` (pedido p/ delivery).

    Uma tool os muta retornando `Command(update={...})` e a lib emite
    `STATE_SNAPSHOT`/`STATE_DELTA` automaticamente; o front os renderiza genericamente. Ver
    `update_reservation` / `update_delivery` em `app/domain/restaurant/tools.py`.
    """

    reservation: dict
    delivery: dict
