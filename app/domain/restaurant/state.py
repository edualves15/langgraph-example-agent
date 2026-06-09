from typing_extensions import TypedDict

from app.agent.state import AgentState


class MenuItem(TypedDict):
    """Item de prato padronizado no rascunho (subconjunto do menu)."""

    name: str
    price: float


class ReservationDraft(TypedDict, total=False):
    """Rascunho da reserva de mesa. `total=False`: todos os campos são opcionais
    (preenchidos incrementalmente conforme o cliente escolhe)."""

    items: list[MenuItem]
    date: str
    time: str
    party_size: int
    customer_name: str


class DeliveryDraft(TypedDict, total=False):
    """Rascunho do pedido de delivery. `total=False`: campos opcionais (incrementais)."""

    items: list[MenuItem]
    customer_name: str
    address: str
    phone: str
    notes: str


class RestaurantState(AgentState):
    """Estende `AgentState` com o estado compartilhado do negócio. Só o fluxo ATIVO fica
    preenchido (o outro `{}`). Mutado por tools via `Command(update={...})` → emite
    `STATE_SNAPSHOT`/`STATE_DELTA`. Ver `update_reservation`/`update_delivery` em `tools.py`.
    """

    reservation: ReservationDraft
    delivery: DeliveryDraft
