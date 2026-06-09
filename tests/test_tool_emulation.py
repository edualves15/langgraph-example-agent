"""Testes da camada de emulação de tool calling (funções puras + a camada)."""

import asyncio

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.agent import tool_emulation as te


@tool
def add(a: int, b: int) -> int:
    """Soma a e b."""
    return a + b


def test_render_tool_instructions_lists_names():
    txt = te.render_tool_instructions([add])
    assert "add" in txt and txt


def test_render_tool_instructions_empty():
    assert te.render_tool_instructions([]) == ""


def test_parse_plain_json_tool_call():
    out = te.parse_tool_call(AIMessage(content='{"tool": "add", "args": {"a": 1, "b": 2}}'), {"add"})
    assert out.tool_calls and out.tool_calls[0]["name"] == "add"
    assert out.tool_calls[0]["args"] == {"a": 1, "b": 2}


def test_parse_fenced_json_tool_call():
    out = te.parse_tool_call(AIMessage(content='```json\n{"tool": "add", "args": {}}\n```'), {"add"})
    assert out.tool_calls and out.tool_calls[0]["name"] == "add"


def test_parse_plain_text_unchanged():
    out = te.parse_tool_call(AIMessage(content="Olá, tudo bem?"), {"add"})
    assert not out.tool_calls and out.content == "Olá, tudo bem?"


def test_parse_unknown_tool_unchanged():
    out = te.parse_tool_call(AIMessage(content='{"tool": "drop_db", "args": {}}'), {"add"})
    assert not out.tool_calls


class _FakeModel:
    def __init__(self, content):
        self._content = content

    async def ainvoke(self, messages, config=None):
        return AIMessage(content=self._content)


def test_layer_produces_tool_call():
    layer = te.ToolCallingEmulationLayer(_FakeModel('{"tool":"add","args":{"a":1,"b":2}}'))
    out = asyncio.run(layer.bind_tools([add]).ainvoke([]))
    assert out.tool_calls and out.tool_calls[0]["name"] == "add"


def test_layer_text_uses_official_emit_hook(monkeypatch):
    emitted = {}

    async def fake_emit(name, data, config=None):
        emitted.update(name=name, data=data)

    monkeypatch.setattr(te, "adispatch_custom_event", fake_emit)
    out = asyncio.run(te.ToolCallingEmulationLayer(_FakeModel("Olá!")).bind_tools([add]).ainvoke([]))
    assert not out.tool_calls
    assert emitted["name"] == "manually_emit_message"
    assert emitted["data"]["message"] == "Olá!"
