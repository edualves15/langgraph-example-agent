from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # Estado temporário por execução: morre ao final da requisição.
    messages: Annotated[list[BaseMessage], add_messages]
    tool_calls_count: int
