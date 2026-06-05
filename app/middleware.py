"""Configuração de middlewares da aplicação FastAPI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


def configure_middlewares(app: FastAPI) -> None:
    """Registra os middlewares no app.

    CORS — permite que QUALQUER frontend AG-UI (outra origem) consuma o agente, que é a
    proposta de desacoplamento do protocolo. Origens via `AG_UI_CORS_ORIGINS`.
    Conformidade: a spec proíbe wildcard `*` com `allow_credentials=True`; por isso
    credenciais só são habilitadas quando as origens são explícitas (não `*`).
    """
    origins = settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
