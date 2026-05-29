from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    tool_calls_count: int


class ToolCallInput(TypedDict):
    """Schema de entrada exclusivo do nó execute_tool (injetado via Send)."""
    messages: Annotated[list[BaseMessage], add_messages]
    tool_calls_count: int
    tool_call: dict
