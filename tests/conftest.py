"""Fixtures e utilitários compartilhados dos testes do servidor.

Os testes rodam **offline e determinísticos**: o LLM nunca é chamado de verdade — os
testes de integração injetam um `StubAgent` em `app.state.agent`, e os testes unitários
exercitam funções puras. Uma `GEMINI_API_KEY` dummy é garantida apenas para que o modelo
seja *construído* (sem rede) durante o lifespan.
"""

import os

# Garante uma chave (não-vazia) antes de importar a app, só para construir o modelo.
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import pytest
from ag_ui.core import (
    EventType,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from fastapi.testclient import TestClient

from app.main import app


class StubAgent:
    """Agente falso que emite eventos AG-UI canônicos (sem LLM).

    Opcionalmente levanta uma exceção após o N-ésimo evento, para exercitar o wrap de
    `RUN_ERROR` do endpoint.
    """

    name = "stub-agent"

    def __init__(self, events=None, raise_after=None):
        self._events = list(events) if events is not None else default_events()
        self._raise_after = raise_after

    def clone(self):
        return self

    async def run(self, input_data):
        for i, event in enumerate(self._events):
            yield event
            if self._raise_after is not None and i == self._raise_after:
                # Mensagem com "segredo"/path para validar que NÃO vaza ao cliente.
                raise RuntimeError("boom-secret /internal/secret/path token=abc123")


def default_events():
    return [
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
        TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id="m", role="assistant"),
        TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id="m", delta="ola"),
        TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id="m"),
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="t", run_id="r"),
    ]


def make_input(content="oi", tools=None):
    """Monta um corpo `RunAgentInput` válido (campos camelCase)."""
    return {
        "threadId": "t1",
        "runId": "r1",
        "state": {},
        "messages": [{"id": "m1", "role": "user", "content": content}],
        "tools": tools or [],
        "context": [],
        "forwardedProps": {},
    }


def sse_event_types(text: str) -> list[str]:
    """Extrai os `type` dos eventos SSE de uma resposta `data: {...}` por linha."""
    import json

    types = []
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                types.append(json.loads(line[5:].strip())["type"])
            except Exception:
                pass
    return types


@pytest.fixture
def client():
    """TestClient com o lifespan ativo (constrói `app.state.agent`)."""
    with TestClient(app) as c:
        yield c
