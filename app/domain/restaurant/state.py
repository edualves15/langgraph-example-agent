from app.agent.state import AgentState


class RestaurantState(AgentState):
    """Estende `AgentState` com o estado compartilhado do negócio. Forma padronizada
    `{ items: [{name, price}], ...campos }`; só o fluxo ATIVO fica preenchido (o outro `{}`):

    - `reservation` = `{ items, date, time, party_size, customer_name }`;
    - `delivery`    = `{ items, customer_name, address, phone, notes }`.

    Mutado por tools via `Command(update={...})` → emite `STATE_SNAPSHOT`/`STATE_DELTA`.
    Ver `update_reservation`/`update_delivery` em `tools.py`.
    """

    reservation: dict
    delivery: dict
