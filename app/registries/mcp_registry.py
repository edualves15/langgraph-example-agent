from langchain_core.tools import BaseTool

from app.mcp.client import load_mcp_tools


async def get_mcp_tools() -> list[BaseTool]:
    return await load_mcp_tools()
