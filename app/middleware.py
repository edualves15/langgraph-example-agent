"""Configuração de middlewares da aplicação FastAPI."""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


class MaxBodySizeMiddleware:
    """Middleware ASGI **puro** que recusa corpos grandes (DoS de memória).

    Checa o header `content-length` ANTES de o app ler o corpo e responde **413** se
    exceder `max_bytes`. Para requisições válidas, **delega intacto** — não envolve a
    resposta, então o streaming SSE do `/agent` é preservado. (Requisições com
    transfer-encoding chunked sem `content-length` não são limitadas por este check.)
    """

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and self.max_bytes > 0:
            cl = dict(scope.get("headers") or {}).get(b"content-length")
            if cl is not None:
                try:
                    too_big = int(cl) > self.max_bytes
                except ValueError:
                    too_big = False
                if too_big:
                    body = json.dumps({"detail": "Requisição grande demais."}).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [(b"content-type", b"application/json")],
                    })
                    await send({"type": "http.response.body", "body": body})
                    return
        await self.app(scope, receive, send)


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
