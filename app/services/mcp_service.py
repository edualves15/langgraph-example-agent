"""Integração MCP (Model Context Protocol) — scaffold padronizado.

Usa o cliente oficial `langchain-mcp-adapters` para expor tools de servidores MCP ao
agente. `MCP_SERVERS` está **vazio** por enquanto (nenhuma conexão); basta adicionar
entradas para habilitar. As tools carregadas aqui são mescladas no grafo via
`build_graph(extra_tools=...)` (ver `app/main.py` / `app/agent/graph.py`).
"""

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

# Servidores MCP a conectar. VAZIO = nenhum servidor por enquanto.
# Formato (langchain-mcp-adapters), por servidor:
#   "nome": {"url": "https://host/mcp", "transport": "streamable_http"}
#   "nome": {"command": "python", "args": ["server.py"], "transport": "stdio"}
MCP_SERVERS: dict[str, dict] = {}


async def get_mcp_tools() -> list[BaseTool]:
    """Carrega as tools dos servidores MCP configurados.

    Retorna `[]` quando `MCP_SERVERS` está vazio (sem qualquer conexão de rede).
    """
    if not MCP_SERVERS:
        return []
    client = MultiServerMCPClient(MCP_SERVERS)
    return await client.get_tools()
