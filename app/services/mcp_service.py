"""Integração MCP (Model Context Protocol) — scaffold padronizado e resiliente.

Usa o cliente oficial `langchain-mcp-adapters` para expor tools de servidores MCP ao
agente. Há **duas origens** de servidores, unidas no composition root (`app/main.py`):

- **gerais** — `mcp.json` na raiz do projeto (capabilities genéricas, sem domínio);
- **de domínio** — `Domain.mcp_servers` (ex.: `app/domain/<dominio>/mcp.json`).

Ambas usam a convenção do ecossistema MCP (chave `mcpServers`) e, por padrão, ficam
**vazias**. As tools carregadas são mescladas no grafo via `build_graph(DOMAIN,
extra_tools=...)`, que ainda **deduplica nomes** (tools de backend confiáveis vencem).

Shape por servidor (langchain-mcp-adapters), em `mcpServers`:
    "nome": {"url": "https://host/mcp", "transport": "streamable_http"}
    "nome": {"command": "python", "args": ["server.py"], "transport": "stdio"}
"""

import asyncio
import json
import logging
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import settings
from app.errors import error_hint

logger = logging.getLogger(__name__)

# mcp.json geral fica na raiz do projeto (app/services/mcp_service.py → parents[2]).
_MCP_CONFIG = Path(__file__).resolve().parents[2] / "mcp.json"


def load_mcp_servers(path: Path) -> dict[str, dict]:
    """Lê o objeto `mcpServers` de um arquivo JSON. Ausente/inválido → `{}`."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return servers if isinstance(servers, dict) else {}


def general_mcp_servers() -> dict[str, dict]:
    """Servidores MCP **gerais** (capabilities genéricas), lidos do `mcp.json` da raiz."""
    return load_mcp_servers(_MCP_CONFIG)


def merge_servers(*server_dicts: dict) -> dict[str, dict]:
    """Une dicts de servidores; em colisão de NOME de servidor mantém o primeiro e loga.

    Os gerais são passados antes dos de domínio ⇒ os gerais têm precedência (nomes de
    servidor devem ser únicos; colisão é sinal de configuração ambígua).
    """
    merged: dict[str, dict] = {}
    for servers in server_dicts:
        for name, cfg in (servers or {}).items():
            if name in merged:
                logger.warning("MCP: servidor '%s' duplicado — definição posterior ignorada.", name)
                continue
            merged[name] = cfg
    return merged


async def get_mcp_tools(servers: dict | None = None) -> list[BaseTool]:
    """Carrega as tools dos servidores MCP, **isolando falhas por servidor**.

    `servers=None` ⇒ usa os servidores gerais (`mcp.json` da raiz). Um servidor
    inacessível/mal configurado é logado (`error_hint`) e **pulado** — não derruba os
    demais nem a inicialização da aplicação. Sem servidores, retorna `[]` (sem rede).
    """
    if servers is None:
        servers = general_mcp_servers()
    if not servers:
        return []
    timeout = settings.ag_ui_mcp_startup_timeout
    tools: list[BaseTool] = []
    for name, cfg in servers.items():
        # Um client por servidor (não um único `MultiServerMCPClient` com todos): assim a
        # falha/timeout de um servidor é isolada e não impede o carregamento dos demais.
        try:
            client = MultiServerMCPClient({name: cfg})
            loaded = client.get_tools()
            if timeout > 0:
                loaded = asyncio.wait_for(loaded, timeout=timeout)
            tools.extend(await loaded)
        except asyncio.TimeoutError:
            logger.warning("MCP: servidor '%s' excedeu o timeout de %.1fs — ignorado.",
                           name, timeout)
        except Exception as exc:  # isola a falha de um servidor dos demais
            logger.warning("MCP: falha ao carregar o servidor '%s' (%s) — ignorado.",
                           name, error_hint(exc))
    return tools
