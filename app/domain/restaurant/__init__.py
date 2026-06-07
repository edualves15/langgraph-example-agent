"""Domínio **Restaurante** — o *plug* de negócio montado sobre o engine genérico.

Este pacote agrupa tudo que é específico do restaurante (tools, estado, prompt, dicas de
UI) e o expõe como um único `DOMAIN: Domain`. O composition root (`app/main.py`) o importa
e passa a `build_graph(DOMAIN, ...)`. Trocar de domínio = trocar este import por outro
pacote que exponha um `DOMAIN`.
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

# Estado preditivo (AG-UI PredictState): ligaria uma chave de estado de TOPO ao argumento de
# uma tool. Vazio: era no-op com o provedor atual (Gemini não faz streaming de
# `TOOL_CALL_ARGS`) e não mapeia para `items` aninhado em `reservation`/`delivery`. O estado
# segue via STATE_SNAPSHOT/DELTA; o grafo trata lista vazia (não emite o evento).
PREDICT_STATE: list[dict] = []

DOMAIN = Domain(
    name="restaurant",
    tools=RESTAURANT_TOOLS,
    state_schema=RestaurantState,
    prompt=_PROMPT,
    predict_state=PREDICT_STATE,
    ui_hints=UI_HINTS,
)
