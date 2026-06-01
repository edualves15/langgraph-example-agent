import json

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.agent.prompts import get_system_prompt
from app.agent.state import AgentState
from app.tools import format_narration_label, get_tool_narration


def _serialize_tool_result(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, default=str)
    return str(result)


def build_agent_node(llm_with_tools, tools_by_name: dict):
    async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
        messages = [SystemMessage(content=get_system_prompt()), *state["messages"]]
        response = await llm_with_tools.ainvoke(messages, config=config)

        for tc in getattr(response, "tool_calls", []):
            meta = get_tool_narration(tools_by_name.get(tc["name"]))
            await adispatch_custom_event(
                "tool_call",
                {
                    "tool_name": tc["name"],
                    "tool_call_id": tc["id"],
                    "text": format_narration_label(meta, tc, tools_by_name),
                    "icon": meta.icon,
                    "args": tc.get("args", {}),
                    "level": meta.level,
                },
                config=config,
            )

        return {"messages": [response]}

    return agent_node


def build_tool_node(tools_by_name: dict):
    async def tool_node(state: AgentState, config: RunnableConfig) -> dict:
        last_message = state["messages"][-1]
        outputs = []

        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_call_id = tool_call["id"]
            tool = tools_by_name[tool_name]
            meta = get_tool_narration(tool)

            try:
                result = await tool.ainvoke(tool_call["args"], config=config)
                await adispatch_custom_event(
                    "tool_result",
                    {
                        "tool": tool_name,
                        "tool_call_id": tool_call_id,
                        "text": meta.done_label or f"{tool_name} concluído",
                        "icon": meta.icon,
                    },
                    config=config,
                )
            except Exception as exc:
                result = f"Erro: {exc}"
                await adispatch_custom_event(
                    "tool_error",
                    {
                        "tool": tool_name,
                        "tool_call_id": tool_call_id,
                        "text": meta.error_label or f"{tool_name} falhou",
                        "icon": meta.icon,
                        "error": str(exc),
                    },
                    config=config,
                )

            outputs.append(
                ToolMessage(
                    content=_serialize_tool_result(result),
                    name=tool_name,
                    tool_call_id=tool_call_id,
                )
            )

        return {"messages": outputs}

    return tool_node
