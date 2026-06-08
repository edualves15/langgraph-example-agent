"""Testes do scaffold MCP: leitura, merge e isolamento de falha por servidor."""

import asyncio

from app.services import mcp_service as m


def test_load_mcp_servers_missing_file(tmp_path):
    assert m.load_mcp_servers(tmp_path / "nope.json") == {}


def test_load_mcp_servers_reads_mcpservers(tmp_path):
    p = tmp_path / "mcp.json"
    p.write_text('{"mcpServers": {"a": {"url": "http://x/mcp"}}}', encoding="utf-8")
    assert m.load_mcp_servers(p) == {"a": {"url": "http://x/mcp"}}


def test_merge_servers_first_wins_on_collision():
    general = {"a": {"url": "g"}, "shared": {"url": "g"}}
    domain = {"b": {"url": "d"}, "shared": {"url": "d"}}
    merged = m.merge_servers(general, domain)
    assert set(merged) == {"a", "b", "shared"}
    assert merged["shared"] == {"url": "g"}  # geral (1º) tem precedência


class _FakeClient:
    """Substitui MultiServerMCPClient: 'bad' levanta; os demais retornam 1 tool fake."""

    def __init__(self, servers):
        self._name = next(iter(servers))

    async def get_tools(self):
        if self._name == "bad":
            raise RuntimeError("conexão recusada")
        return [object()]  # tool fake (a contagem é o que importa aqui)


def test_get_mcp_tools_isolates_failures(monkeypatch):
    monkeypatch.setattr(m, "MultiServerMCPClient", _FakeClient)
    servers = {"ok1": {"url": "x"}, "bad": {"url": "y"}, "ok2": {"url": "z"}}
    tools = asyncio.run(m.get_mcp_tools(servers))
    # 'bad' é pulado; os dois bons entram — um servidor com falha não derruba o resto.
    assert len(tools) == 2


def test_get_mcp_tools_empty_returns_list():
    assert asyncio.run(m.get_mcp_tools({})) == []


class _SlowClient:
    """Substitui MultiServerMCPClient: 'slow' demora demais; os demais retornam rápido."""

    def __init__(self, servers):
        self._name = next(iter(servers))

    async def get_tools(self):
        if self._name == "slow":
            await asyncio.sleep(5)  # excede o timeout baixo do teste
        return [object()]


def test_get_mcp_tools_skips_server_on_timeout(monkeypatch):
    monkeypatch.setattr(m, "MultiServerMCPClient", _SlowClient)
    monkeypatch.setattr(m.settings, "ag_ui_mcp_startup_timeout", 0.05)
    servers = {"ok1": {"url": "x"}, "slow": {"url": "y"}, "ok2": {"url": "z"}}
    tools = asyncio.run(m.get_mcp_tools(servers))
    # 'slow' estoura o timeout e é pulado; os dois rápidos entram (startup não trava).
    assert len(tools) == 2
