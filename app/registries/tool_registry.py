from langchain_core.tools import BaseTool

from app.config import settings
from app.tools.calendar_tools import (
    add_business_days,
    calculate_date_difference,
    count_business_days,
    find_next_weekday,
    get_date_details,
    get_today_info,
    list_dates_in_range,
    shift_date,
)
from app.tools.math_tools import calculate_math_expression
from app.tools.restaurant_tools import (
    create_delivery_order,
    create_reservation,
    get_available_times,
    get_menu,
    update_delivery,
    update_reservation,
)

CALENDAR_TOOLS = [
    get_today_info,
    get_date_details,
    calculate_date_difference,
    shift_date,
    count_business_days,
    add_business_days,
    find_next_weekday,
    list_dates_in_range,
]

# Tools do domínio atual (Restaurante). Dois fluxos: reserva de mesa e pedido p/ delivery.
# Trocar de domínio = trocar este bloco.
RESTAURANT_TOOLS = [
    get_menu,
    get_available_times,
    update_reservation,
    create_reservation,
    update_delivery,
    create_delivery_order,
]

# Estado preditivo (AG-UI PredictState): ligaria uma chave de estado de TOPO ao argumento de
# uma tool, para a UI prever o estado a partir dos args em streaming. Removido: era no-op com
# o provedor atual (Gemini não faz streaming de `TOOL_CALL_ARGS`) e não mapeia para `items`
# aninhado em `reservation`/`delivery`. O estado segue via STATE_SNAPSHOT/DELTA. O grafo trata
# lista vazia (não emite o evento). Ver app/agent/graph.py.
PREDICT_STATE: list[dict] = []


def get_local_tools() -> list[BaseTool]:
    tools: list[BaseTool] = [
        *CALENDAR_TOOLS,
        calculate_math_expression,
        *RESTAURANT_TOOLS,
    ]
    if settings.tavily_api_key:
        from app.tools.web_search import web_search, web_extract
        tools += [web_search, web_extract]
    return tools
