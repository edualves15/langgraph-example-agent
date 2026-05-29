import json
from typing import Any

from app.config import settings


async def load_mcp_tools() -> list[Any]:
    """Carrega tools MCP opcionalmente.

    Mantém MCP fora da API pública. As tools MCP entram apenas no registry interno
    do agente. Requer langchain-mcp-adapters configurado no ambiente.
    """
    if not settings.mcp_enabled:
        return []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    servers = json.loads(settings.mcp_servers_json or "{}")
    if not servers:
        return []

    client = MultiServerMCPClient(servers)
    return await client.get_tools()
