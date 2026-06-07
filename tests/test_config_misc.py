"""Testes de config, registry, prompts e mcp_service (funções puras)."""

from app.config import Settings
from app.registries.tool_registry import get_local_tools


def test_cors_origins_parsing():
    assert Settings(ag_ui_cors_origins="*").cors_origins == ["*"]
    assert Settings(ag_ui_cors_origins="https://a.com, https://b.com ").cors_origins == [
        "https://a.com",
        "https://b.com",
    ]


def test_local_tools_are_generic_only():
    # get_local_tools() são as capabilities GENÉRICAS (sem domínio).
    names = {t.name for t in get_local_tools()}
    assert {"calculate_math_expression", "get_today_info"} <= names
    # As tools do domínio NÃO vêm daqui (entram via Domain.tools).
    assert not ({"get_menu", "update_reservation", "create_delivery_order"} & names)


def test_restaurant_domain_bundle():
    from app.domain.restaurant import DOMAIN

    names = {t.name for t in DOMAIN.tools}
    assert {
        "get_menu", "update_reservation", "update_delivery",
        "create_reservation", "create_delivery_order", "get_available_times",
    } <= names
    assert DOMAIN.name == "restaurant"
    # state_schema declara as chaves de estado do domínio.
    assert {"reservation", "delivery"} <= set(DOMAIN.state_schema.__annotations__)
    # ui_hints entregues ao front via CUSTOM.
    assert "state_tag_icons" in DOMAIN.ui_hints and "state_titles" in DOMAIN.ui_hints
    # PredictState removido (no-op com Gemini; não cabe no `items` aninhado).
    assert DOMAIN.predict_state == []
    # MCP do domínio: vazio por padrão (placeholder app/domain/restaurant/mcp.json).
    assert DOMAIN.mcp_servers == {}


def test_system_prompt_injects_date():
    from datetime import date

    from app.agent.prompts import get_system_prompt

    prompt = get_system_prompt()
    assert "{{TODAY}}" not in prompt
    assert date.today().strftime("%d/%m/%Y") in prompt


def test_mcp_servers_empty_by_default():
    import asyncio

    from app.services.mcp_service import general_mcp_servers, get_mcp_tools

    assert general_mcp_servers() == {}
    assert asyncio.run(get_mcp_tools()) == []
