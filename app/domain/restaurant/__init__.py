"""Domínio **Restaurante** — agrupa tools, estado, prompt e dicas de UI específicos do
negócio e os expõe como um único `DOMAIN: Domain`, consumido por `app/main.py`.
"""

from importlib.resources import files

from app.agent.domain import Domain
from app.domain.restaurant.state import RestaurantState
from app.domain.restaurant.tools import (
    create_delivery_order,
    create_reservation,
    get_available_times,
    get_menu,
    update_delivery,
    update_reservation,
)
from app.domain.restaurant.ui_hints import UI_HINTS

# Tools de backend do domínio. Dois fluxos: reserva de mesa e pedido p/ delivery.
RESTAURANT_TOOLS = [
    get_menu,
    get_available_times,
    update_reservation,
    create_reservation,
    update_delivery,
    create_delivery_order,
]

_PROMPT = files(__package__).joinpath("prompt.md").read_text(encoding="utf-8").strip()

# Estado preditivo (AG-UI PredictState): vazio — no-op com Gemini (não faz streaming de
# `TOOL_CALL_ARGS`) e não cabe no `items` aninhado. O estado segue via STATE_SNAPSHOT/DELTA.
PREDICT_STATE: list[dict] = []

DOMAIN = Domain(
    name="restaurant",
    tools=RESTAURANT_TOOLS,
    state_schema=RestaurantState,
    prompt=_PROMPT,
    predict_state=PREDICT_STATE,
    ui_hints=UI_HINTS,
)
