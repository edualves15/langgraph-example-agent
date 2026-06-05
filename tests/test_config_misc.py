"""Testes de config, registry, prompts e mcp_service (funções puras)."""

from app.config import Settings
from app.registries.tool_registry import PREDICT_STATE, get_local_tools


def test_cors_origins_parsing():
    assert Settings(ag_ui_cors_origins="*").cors_origins == ["*"]
    assert Settings(ag_ui_cors_origins="https://a.com, https://b.com ").cors_origins == [
        "https://a.com",
        "https://b.com",
    ]


def test_local_tools_and_predict_state():
    names = {t.name for t in get_local_tools()}
    assert {"calculate_math_expression", "get_today_info", "get_menu", "update_reservation"} <= names
    assert PREDICT_STATE == [
        {"state_key": "order", "tool": "update_reservation", "tool_argument": "item_ids"}
    ]


def test_system_prompt_injects_date():
    from datetime import date

    from app.agent.prompts import get_system_prompt

    prompt = get_system_prompt()
    assert "{{TODAY}}" not in prompt
    assert date.today().strftime("%d/%m/%Y") in prompt


def test_mcp_servers_empty_by_default():
    import asyncio

    from app.services.mcp_service import _load_servers, get_mcp_tools

    assert _load_servers() == {}
    assert asyncio.run(get_mcp_tools()) == []
