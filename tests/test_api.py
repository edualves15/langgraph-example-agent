"""Testes de integração do servidor FastAPI (com agente stubado — sem LLM real)."""

from ag_ui.core import (
    CustomEvent,
    EventType,
    RawEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageStartEvent,
)

from conftest import StubAgent, default_events, make_input, sse_event_types


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_cors_preflight(client):
    r = client.options(
        "/agent/stream",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


def test_invalid_body_returns_422(client):
    r = client.post("/agent/stream", json={"not": "valid"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_agent_sse_happy_path(client):
    client.app.state.agent = StubAgent()  # eventos canônicos, sem LLM
    r = client.post("/agent/stream", json=make_input())
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    types = sse_event_types(r.text)
    assert types[0] == "RUN_STARTED"
    assert "TEXT_MESSAGE_CONTENT" in types
    assert types[-1] == "RUN_FINISHED"


def test_agent_emits_ui_hints_custom_after_run_started(client):
    # As dicas de UI do domínio são entregues ao front via evento CUSTOM (ui_hints),
    # logo após o RUN_STARTED. O agente é stubado; ui_hints vem do lifespan (DOMAIN).
    client.app.state.agent = StubAgent()
    r = client.post("/agent/stream", json=make_input())
    types = sse_event_types(r.text)
    assert types[0] == "RUN_STARTED"
    assert types[1] == "CUSTOM"  # emitido imediatamente após o RUN_STARTED
    assert '"name":"ui_hints"' in r.text
    assert "state_tag_icons" in r.text and "state_titles" in r.text


def test_agent_no_ui_hints_when_unset(client):
    # Sem ui_hints no app.state (domínio sem dicas), nenhum CUSTOM é emitido.
    client.app.state.agent = StubAgent()
    client.app.state.ui_hints = None
    r = client.post("/agent/stream", json=make_input())
    types = sse_event_types(r.text)
    assert "CUSTOM" not in types


def test_agent_run_error_wrap_is_safe(client):
    # Stub levanta após o 1º evento → o wrap deve emitir RUN_ERROR genérico (sem vazar).
    client.app.state.agent = StubAgent(events=default_events(), raise_after=0)
    r = client.post("/agent/stream", json=make_input())
    assert r.status_code == 200
    types = sse_event_types(r.text)
    assert "RUN_ERROR" in types
    # Mensagem genérica; não vaza o texto cru da exceção.
    assert "boom-secret" not in r.text
    assert "/internal/secret/path" not in r.text


def test_agent_invoke_happy_path(client):
    # Rota síncrona: agrega os eventos do run num único corpo JSON.
    client.app.state.agent = StubAgent()  # default_events → texto "ola", sem estado/interrupt
    r = client.post("/agent/invoke", json=make_input())
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "ola"
    assert body["threadId"] == "t1" and body["runId"] == "r1"
    assert body["state"] == {}
    assert body["interrupt"] is None


def test_agent_invoke_aggregates_state_and_interrupt(client):
    # content = mensagem FINAL (o preâmbulo é descartado ao chegar novo TEXT_MESSAGE_START);
    # state = último snapshot sem chaves protocolares; interrupt = value do CUSTOM on_interrupt.
    events = [
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
        TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id="m0", role="assistant"),
        TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id="m0", delta="preambulo"),
        StateSnapshotEvent(
            type=EventType.STATE_SNAPSHOT,
            snapshot={"reservation": {"party_size": 4}, "messages": [1], "tools": [2]},
        ),
        TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id="m1", role="assistant"),
        TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id="m1", delta="final"),
        CustomEvent(type=EventType.CUSTOM, name="on_interrupt", value={"question": "Confirmar?"}),
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="t", run_id="r"),
    ]
    client.app.state.agent = StubAgent(events=events)
    body = client.post("/agent/invoke", json=make_input()).json()
    assert body["content"] == "final"  # preâmbulo descartado
    assert body["state"] == {"reservation": {"party_size": 4}}  # messages/tools removidos
    assert body["interrupt"] == {"question": "Confirmar?"}


def test_agent_invoke_run_error_event_becomes_500(client):
    # Um RUN_ERROR no stream vira 500 JSON (ErrorResponse), não um 200 com erro embutido.
    client.app.state.agent = StubAgent(events=[
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
        RunErrorEvent(type=EventType.RUN_ERROR, message="algo falhou", code="x"),
    ])
    r = client.post("/agent/invoke", json=make_input())
    assert r.status_code == 500
    assert r.json()["detail"] == "algo falhou"


def test_agent_invoke_exception_wrap_is_safe(client):
    # Exceção crua durante o run → 500 genérico (sem vazar texto da exceção).
    client.app.state.agent = StubAgent(events=default_events(), raise_after=0)
    r = client.post("/agent/invoke", json=make_input())
    assert r.status_code == 500
    assert "boom-secret" not in r.text and "/internal/secret/path" not in r.text


def test_openapi_schemas_dtos_and_input(client):
    # Schemas traz nossos DTOs (+ aninhados) E o contrato de entrada tipado (RunAgentInput).
    spec = client.get("/openapi.json").json()
    schemas = set(spec["components"]["schemas"])
    assert {"ErrorResponse", "HealthResponse", "AgentInvokeResponse"} <= schemas
    assert "RunAgentInput" in schemas  # input do agente tipado pelo modelo oficial
    # Nenhum $ref pendente (todos os refs resolvem para um schema existente).
    import json
    import re
    refs = set(re.findall(r"#/components/schemas/([A-Za-z0-9_]+)", json.dumps(spec)))
    assert not (refs - schemas)


def test_openapi_agent_operation_documented(client):
    post = client.get("/openapi.json").json()["paths"]["/agent/stream"]["post"]
    # 200 é só SSE (output referenciado como catálogo de eventos); erros documentados.
    assert list(post["responses"]["200"]["content"]) == ["text/event-stream"]
    assert {"413", "422", "500"} <= set(post["responses"])
    # Input tipado por RunAgentInput ($ref) + exemplo no Swagger ("Try it out").
    body = post["requestBody"]["content"]["application/json"]
    assert body["schema"]["$ref"].endswith("/RunAgentInput")
    assert "examples" in body


def test_docs_available_by_default(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_kwargs_toggle():
    from app.main import _docs_kwargs
    assert _docs_kwargs(True) == {
        "docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json",
    }
    assert _docs_kwargs(False) == {"docs_url": None, "redoc_url": None, "openapi_url": None}


def test_raw_events_filtered_when_disabled(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ag_ui_stream_raw_events", False)
    client.app.state.agent = StubAgent(events=[
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
        RawEvent(type=EventType.RAW, event={"x": 1}),
    ])
    r = client.post("/agent/stream", json=make_input())
    types = sse_event_types(r.text)
    assert "RUN_STARTED" in types
    assert "RAW" not in types
