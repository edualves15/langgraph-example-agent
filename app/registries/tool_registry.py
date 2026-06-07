from langchain_core.tools import BaseTool

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


def get_local_tools() -> list[BaseTool]:
    """Tools de backend **genéricas** (sem domínio): calendário e matemática. As tools do
    domínio NÃO vêm daqui — entram no grafo via `Domain.tools` (ver `build_graph(domain,
    ...)` em `app/agent/graph.py`). Capacidades externas (ex.: busca web) ficam a cargo do
    consumidor, via servidores MCP em `mcp.json` (ver `app/services/mcp_service.py`).
    """
    return [*CALENDAR_TOOLS, calculate_math_expression]

