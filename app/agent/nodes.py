from langchain_core.messages import SystemMessage

from app.agent.prompts import get_system_prompt
from app.agent.state import AgentState


def build_agent_node(llm_with_tools):
    async def agent_node(state: AgentState) -> dict:
        messages = [SystemMessage(
            content=get_system_prompt()), *state["messages"]]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    return agent_node
