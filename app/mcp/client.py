import json
from typing import Any

from app.config import settings

_mcp_client = None


async def load_mcp_tools() -> list[Any]:
    """Abre conexões MCP e retorna as tools. Chamado no startup via lifespan."""
    global _mcp_client

    if not settings.mcp_enabled:
        return []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    servers = json.loads(settings.mcp_servers_json or "{}")
    if not servers:
        return []

    _mcp_client = MultiServerMCPClient(servers)
    await _mcp_client.__aenter__()
    return await _mcp_client.get_tools()


async def shutdown_mcp_client() -> None:
    """Fecha conexões MCP. Chamado no shutdown via lifespan."""
    global _mcp_client

    if _mcp_client is not None:
        await _mcp_client.__aexit__(None, None, None)
        _mcp_client = None
