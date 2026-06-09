"""Camada de emulação de tool calling (e de modelos sem streaming nativo).

É só isto: uma **CAMADA** fina que embrulha um chat model **não-conforme** (sem function
calling nativo e/ou sem streaming de tokens) e expõe a **mesma interface** que o grafo já
usa — `bind_tools(...).ainvoke(...)` devolvendo um `AIMessage` (com `tool_calls` quando for o
caso). Ela:

1. injeta as ferramentas no prompt (em vez de `bind_tools` nativo) e faz **parse** da resposta
   textual de volta em `tool_calls`;
2. como faz uma chamada **única** (sem streaming), emite o texto do assistente pelo **hook
   oficial** da lib `ag_ui_langgraph` (evento custom ``manually_emit_message``) — assim o chat
   renderiza mesmo com providers que devolvem um JSON pronto.

É a **única** peça que conhece esse "truque": o grafo (`app/agent/graph.py`) trata o resultado
como um modelo comum, **sem nenhum `if`**. Fallback best-effort: assume 1 tool call por turno
(igual ao resto do grafo) e depende de o modelo emitir o JSON pedido.

Acoplamento: usa apenas `langchain_core`/LangGraph; o nome do evento custom
(``manually_emit_message``) é o **contrato público** consumido pela lib AG-UI no router —
mantido como string para não importar a lib no engine.
"""

from __future__ import annotations

import json
import re
import uuid

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

# Contrato AG-UI (ag_ui_langgraph): um evento custom com este nome vira TEXT_MESSAGE_* no wire.
_EMIT_MESSAGE_EVENT = "manually_emit_message"

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _openai_specs(tools) -> list[dict]:
    """Normaliza tools de backend (`BaseTool`) e schemas de frontend (`dict`) p/ o formato
    OpenAI `{name, description, parameters}` (descartando o que não converter)."""
    specs: list[dict] = []
    for tool in tools or []:
        try:
            fn = convert_to_openai_tool(tool)["function"]
        except Exception:
            continue
        specs.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return specs


def render_tool_instructions(tools) -> str:
    """Fragmento de system que ensina o modelo a "chamar" uma ferramenta por JSON."""
    specs = _openai_specs(tools)
    if not specs:
        return ""
    lines = [
        "You have tools available. To call ONE tool, reply with ONLY a single-line JSON "
        'object and nothing else: {"tool": "<name>", "args": { ... }}.',
        "Do not wrap it in code fences or prose. To answer the user instead, reply normally "
        "with NO JSON. Available tools:",
    ]
    for s in specs:
        lines.append(
            f"- {s['name']}: {s['description']} "
            f"params={json.dumps(s['parameters'], ensure_ascii=False)}"
        )
    return "\n".join(lines)


def parse_tool_call(message: AIMessage, valid_names: set[str]) -> AIMessage:
    """Se o conteúdo for um JSON `{tool, args}` com `tool` válida, devolve um `AIMessage` com
    `tool_calls`; senão devolve a mensagem original (resposta de texto)."""
    text = message.content if isinstance(message.content, str) else ""
    raw = text.strip()
    if raw.startswith("```"):  # tolera cercas ```json ... ```
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw).strip().rstrip("`").strip()
    match = _JSON_OBJECT.search(raw)
    if not match:
        return message
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return message
    name = data.get("tool") if isinstance(data, dict) else None
    if not name or name not in valid_names:
        return message
    args = data.get("args")
    return AIMessage(
        content="",
        tool_calls=[{
            "name": name,
            "args": args if isinstance(args, dict) else {},
            "id": f"call_{uuid.uuid4().hex[:24]}",
        }],
    )


class ToolCallingEmulationLayer:
    """Veja o docstring do módulo. Embrulha um `BaseChatModel` e imita
    `bind_tools` + `AIMessage.tool_calls`, emitindo o texto pelo hook oficial da lib."""

    def __init__(self, model: BaseChatModel, tools=()) -> None:
        self._model = model
        self._instructions = render_tool_instructions(tools)
        self._names = {s["name"] for s in _openai_specs(tools)}

    def bind_tools(self, tools, **_: object) -> "ToolCallingEmulationLayer":
        return ToolCallingEmulationLayer(self._model, tools)

    async def ainvoke(self, messages, config=None) -> AIMessage:
        msgs = list(messages)
        if self._instructions:
            msgs = [*msgs, SystemMessage(content=self._instructions)]
        response = await self._model.ainvoke(msgs, config=config)
        if not isinstance(response, AIMessage):
            return response
        parsed = parse_tool_call(response, self._names)
        if parsed.tool_calls:
            return parsed  # tool call: back/front leem de AIMessage.tool_calls (sem texto)
        # Resposta de texto: como não houve streaming, emite pelo hook oficial p/ o chat render.
        if isinstance(parsed.content, str) and parsed.content.strip():
            await adispatch_custom_event(
                _EMIT_MESSAGE_EVENT,
                {"message_id": uuid.uuid4().hex, "message": parsed.content},
                config=config,
            )
        return parsed
