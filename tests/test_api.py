"""Testes de integração do servidor FastAPI (com agente stubado — sem LLM real)."""

from ag_ui.core import EventType, RawEvent, RunStartedEvent

from conftest import StubAgent, default_events, make_input, sse_event_types


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_agent_health(client):
    r = client.get("/agent/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "name" in r.json()["agent"]


def test_cors_preflight(client):
    r = client.options(
        "/agent",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


def test_invalid_body_returns_422(client):
    r = client.post("/agent", json={"not": "valid"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_agent_sse_happy_path(client):
    client.app.state.agent = StubAgent()  # eventos canônicos, sem LLM
    r = client.post("/agent", json=make_input())
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    types = sse_event_types(r.text)
    assert types[0] == "RUN_STARTED"
    assert "TEXT_MESSAGE_CONTENT" in types
    assert types[-1] == "RUN_FINISHED"


def test_agent_run_error_wrap_is_safe(client):
    # Stub levanta após o 1º evento → o wrap deve emitir RUN_ERROR genérico (sem vazar).
    client.app.state.agent = StubAgent(events=default_events(), raise_after=0)
    r = client.post("/agent", json=make_input())
    assert r.status_code == 200
    types = sse_event_types(r.text)
    assert "RUN_ERROR" in types
    # Mensagem genérica; não vaza o texto cru da exceção.
    assert "boom-secret" not in r.text
    assert "/internal/secret/path" not in r.text


def test_raw_events_filtered_when_disabled(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ag_ui_stream_raw_events", False)
    client.app.state.agent = StubAgent(events=[
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
        RawEvent(type=EventType.RAW, event={"x": 1}),
    ])
    r = client.post("/agent", json=make_input())
    types = sse_event_types(r.text)
    assert "RUN_STARTED" in types
    assert "RAW" not in types
