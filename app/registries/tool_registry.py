from langchain_core.tools import BaseTool

from app.config import settings
from app.tools.calculator import calculator
from app.tools.calendar import get_events, today


def get_local_tools() -> list[BaseTool]:
    tools: list[BaseTool] = [calculator, get_events, today]
    if settings.tavily_api_key:
        from app.tools.web_search import web_search, web_extract
        tools += [web_search, web_extract]
    return tools
