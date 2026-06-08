"""Configuração de middlewares da aplicação FastAPI."""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


class MaxBodySizeMiddleware:
    """Middleware ASGI **puro** que recusa corpos grandes (DoS de memória).

    Duas linhas de defesa, ANTES de o app processar o corpo:
    1. **fast-path**: se o header `content-length` excede `max_bytes`, responde **413**.
    2. **streaming**: envolve `receive` e soma os bytes do corpo à medida que chegam;
       ao exceder, responde **413** e sinaliza `http.disconnect` ao app — cobrindo
       requisições `transfer-encoding: chunked` (sem `content-length`).

    Só o CORPO da requisição é envolvido; o `send` (resposta) é intacto, preservando o
    streaming SSE do `/stream`.
    """

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    @staticmethod
    async def _reject(send) -> None:
        body = json.dumps({"detail": "Requisição grande demais."}).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or self.max_bytes <= 0:
            await self.app(scope, receive, send)
            return

        cl = dict(scope.get("headers") or []).get(b"content-length")
        if cl is not None:
            try:
                too_big = int(cl) > self.max_bytes
            except ValueError:
                too_big = False
            if too_big:
                await self._reject(send)
                return

        received = 0
        rejected = False

        async def limited_receive():
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes and not rejected:
                    rejected = True
                    await self._reject(send)
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, limited_receive, send)


def configure_middlewares(app: FastAPI) -> None:
    """Registra os middlewares no app.

    - **Limite de corpo** (`MaxBodySizeMiddleware`): recusa POSTs gigantes (DoS).
    - **CORS** (`CORSMiddleware`): permite que QUALQUER frontend AG-UI (outra origem)
      consuma o agente — o desacoplamento do protocolo. Origens via `AG_UI_CORS_ORIGINS`.
      Conformidade: a spec proíbe wildcard `*` com `allow_credentials=True`; por isso
      credenciais só são habilitadas quando as origens são explícitas (não `*`).
    """
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.ag_ui_max_body_bytes)

    origins = settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
