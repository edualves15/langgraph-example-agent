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
    create_reservation,
    get_available_times,
    get_menu,
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

# Tools do domínio atual (Restaurante). Trocar de domínio = trocar este bloco.
RESTAURANT_TOOLS = [get_menu, get_available_times, create_reservation]


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
