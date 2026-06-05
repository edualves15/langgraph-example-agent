"""Integração MCP (Model Context Protocol) — scaffold padronizado.

Usa o cliente oficial `langchain-mcp-adapters` para expor tools de servidores MCP ao
agente. Os servidores são lidos de **`mcp.json`** na raiz do projeto (convenção do
ecossistema MCP: chave `mcpServers`), hoje **vazio** (nenhuma conexão). Para habilitar,
adicione entradas em `mcp.json` — sem mexer em código. As tools carregadas aqui são
mescladas no grafo via `build_graph(extra_tools=...)` (ver `app/main.py`).

Shape por servidor (langchain-mcp-adapters), em `mcpServers`:
    "nome": {"url": "https://host/mcp", "transport": "streamable_http"}
    "nome": {"command": "python", "args": ["server.py"], "transport": "stdio"}
"""

import json
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

# mcp.json fica na raiz do projeto (app/services/mcp_service.py → parents[2]).
_MCP_CONFIG = Path(__file__).resolve().parents[2] / "mcp.json"


def _load_servers() -> dict[str, dict]:
    """Lê o objeto `mcpServers` de `mcp.json`. Ausente/vazio → {}."""
    try:
        data = json.loads(_MCP_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return servers if isinstance(servers, dict) else {}


async def get_mcp_tools() -> list[BaseTool]:
    """Carrega as tools dos servidores MCP configurados em `mcp.json`.

    Retorna `[]` quando não há servidores (sem qualquer conexão de rede).
    """
    servers = _load_servers()
    if not servers:
        return []
    client = MultiServerMCPClient(servers)
    return await client.get_tools()
