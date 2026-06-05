from app.agent.graph import _frontend_tool_schemas, build_graph


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
    graph = build_graph()
    nodes = set(graph.get_graph().nodes)
    assert {"agent", "tools"} <= nodes


def test_build_graph_accepts_extra_tools():
    # extra_tools vazio (MCP) não quebra a construção.
    assert build_graph(extra_tools=[]) is not None
