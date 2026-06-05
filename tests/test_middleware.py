import pytest

from app.middleware import MaxBodySizeMiddleware


class _Recorder:
    """App ASGI interno falso: registra se foi chamado e captura mensagens enviadas."""

    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _drive(mw, content_length):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    scope = {
        "type": "http",
        "headers": [(b"content-length", str(content_length).encode())],
    }
    await mw(scope, receive, send)
    return sent


@pytest.mark.asyncio
async def test_rejects_oversized_body():
    inner = _Recorder()
    mw = MaxBodySizeMiddleware(inner, max_bytes=100)
    sent = await _drive(mw, content_length=200)
    assert sent[0]["status"] == 413
    assert inner.called is False  # nunca delega ao app


@pytest.mark.asyncio
async def test_passes_small_body_through():
    inner = _Recorder()
    mw = MaxBodySizeMiddleware(inner, max_bytes=100)
    sent = await _drive(mw, content_length=50)
    assert inner.called is True
    assert sent[0]["status"] == 200


@pytest.mark.asyncio
async def test_disabled_when_limit_zero():
    inner = _Recorder()
    mw = MaxBodySizeMiddleware(inner, max_bytes=0)
    sent = await _drive(mw, content_length=10_000_000)
    assert inner.called is True
    assert sent[0]["status"] == 200
