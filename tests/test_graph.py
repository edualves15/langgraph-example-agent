from langchain_core.tools import tool

from app.agent.graph import _frontend_tool_schemas, _merge_backend_tools, build_graph
from app.domain.restaurant import DOMAIN


def test_frontend_tool_schemas_conversion():
    tools = [
        {"name": "present_cards", "description": "d", "parameters": {"type": "object", "properties": {}}},
        {"name": "no_params"},  # sem parameters → default object vazio
    ]
    out = _frontend_tool_schemas(tools, exclude=set())
    assert [s["function"]["name"] for s in out] == ["present_cards", "no_params"]
    assert out[0]["type"] == "function"
    assert out[1]["function"]["parameters"] == {"type": "object", "properties": {}}


def test_frontend_tool_schemas_excludes_collisions():
    tools = [{"name": "calculate_math_expression", "description": "x", "parameters": {}}]
    # Colisão com tool de backend → excluída (o backend vence).
    assert _frontend_tool_schemas(tools, exclude={"calculate_math_expression"}) == []


def test_build_graph_compiles_with_nodes():
    graph = build_graph(DOMAIN)
    nodes = set(graph.get_graph().nodes)
    assert {"agent", "tools"} <= nodes


def test_build_graph_accepts_extra_tools():
    # extra_tools vazio (MCP) não quebra a construção.
    assert build_graph(DOMAIN, extra_tools=[]) is not None


def test_build_graph_compiles_with_emulation_layer(monkeypatch):
    # Com a camada de emulação ligada, o grafo (transparente à camada) ainda compila.
    import app.services.llm_service as llm

    monkeypatch.setattr(llm.settings, "llm_tool_emulation", True)
    monkeypatch.setattr(llm.settings, "llm_api_key", "k")
    graph = build_graph(DOMAIN)
    assert {"agent", "tools"} <= set(graph.get_graph().nodes)


def test_merge_backend_tools_dedups_collisions():
    @tool
    def get_menu() -> str:
        """Fake colidente com a tool de backend get_menu."""
        return "x"

    @tool
    def external_only() -> str:
        """Tool externa sem colisão."""
        return "y"

    primary = list(DOMAIN.tools)  # inclui o get_menu real
    merged = _merge_backend_tools(primary, [get_menu, external_only])
    names = [t.name for t in merged]
    # A externa colidente (get_menu) é descartada; a não-colidente entra.
    assert names.count("get_menu") == 1
    assert "external_only" in names
    assert len(merged) == len(primary) + 1


def test_build_graph_with_colliding_extra_tool_compiles():
    @tool
    def get_menu() -> str:
        """Fake colidente."""
        return "x"

    graph = build_graph(DOMAIN, extra_tools=[get_menu])
    assert {"agent", "tools"} <= set(graph.get_graph().nodes)
