from langchain_core.tools import BaseTool

from app.tools.calculator import calculator
from app.tools.calendar import get_events, today


def get_local_tools() -> list[BaseTool]:
    # Tools privadas: não são endpoints HTTP.
    return [calculator, get_events, today]
