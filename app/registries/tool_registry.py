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
from app.tools.agui_demo_tools import add_proverb, request_approval, set_proverbs
from app.tools.math_tools import calculate_math_expression

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

# Ferramentas que demonstram estado compartilhado (STATE_*) e human-in-the-loop.
AGUI_DEMO_TOOLS = [add_proverb, set_proverbs, request_approval]


def get_local_tools() -> list[BaseTool]:
    tools: list[BaseTool] = [
        *CALENDAR_TOOLS,
        calculate_math_expression,
        *AGUI_DEMO_TOOLS,
    ]
    if settings.tavily_api_key:
        from app.tools.web_search import web_search, web_extract
        tools += [web_search, web_extract]
    return tools
