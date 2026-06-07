"""Router do endpoint AG-UI (`/agent`) sobre LangGraph.

Replica os primitivos oficiais (`agent.clone().run(input)` + `EventEncoder`), mas com um
**wrap fino de erro**: em qualquer exceção, emite um `RUN_ERROR` (`code="agent_run_error"`)
— evento **canônico** do protocolo para falhas — em vez de derrubar o SSE cru. O agente vem
de `request.app.state.agent` (criado no lifespan, ver `app/main.py`).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import cast

from ag_ui.core import CustomEvent, EventType, RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.errors import describe_error, error_hint
from app.schemas import AgentHealthResponse, AgentInfo, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])


def get_agent(request: Request) -> LangGraphAgent:
    """Acesso **tipado** ao agente AG-UI guardado em `app.state` (criado no lifespan)."""
    return cast(LangGraphAgent, request.app.state.agent)


# Respostas documentadas no OpenAPI. O 200 é um stream SSE (text/event-stream); os erros
# usam o DTO ErrorResponse (`{"detail": "..."}`), coerente com os handlers/middleware.
_AGENT_RESPONSES: dict = {
    200: {
        "description": (
            "Stream SSE (text/event-stream) de eventos AG-UI: RUN_STARTED, "
            "TEXT_MESSAGE_* , TOOL_CALL_* , STATE_* , CUSTOM (ex.: ui_hints), "
            "RUN_FINISHED/RUN_ERROR e RAW (omitível via AG_UI_STREAM_RAW_EVENTS)."
        ),
        "content": {"text/event-stream": {}},
    },
    413: {"model": ErrorResponse, "description": "Corpo da requisição acima do limite."},
    422: {"model": ErrorResponse, "description": "Corpo inválido (não corresponde a RunAgentInput)."},
    500: {"model": ErrorResponse, "description": "Erro inesperado ao processar a requisição."},
}


@router.post(
    "/agent",
    summary="Executa o agente e transmite eventos AG-UI (SSE)",
    responses=_AGENT_RESPONSES,
)
async def agent_endpoint(input_data: RunAgentInput, request: Request) -> StreamingResponse:
    """Roda o agente para um `RunAgentInput` (protocolo AG-UI) e devolve o resultado como
    um stream **SSE** de eventos AG-UI. Erros são emitidos como `RUN_ERROR` dentro do
    stream; falhas pré-stream usam o formato `ErrorResponse`."""
    encoder = EventEncoder(accept=request.headers.get("accept"))
    request_agent = get_agent(request).clone()  # estado isolado por requisição (oficial)
    # Dicas de apresentação do domínio (ícones/títulos do resumo), entregues ao front
    # genérico pelo canal oficial AG-UI (evento CUSTOM), logo após o RUN_STARTED — sem
    # canal HTTP paralelo. O front (web/app.js) trata `name="ui_hints"` genericamente.
    ui_hints: dict | None = getattr(request.app.state, "ui_hints", None)

    async def event_generator() -> AsyncIterator[str]:
        hints_sent = False
        try:
            async for event in request_agent.run(input_data):
                if not settings.ag_ui_stream_raw_events and event.type == EventType.RAW:
                    continue
                yield encoder.encode(event)
                if not hints_sent and event.type == EventType.RUN_STARTED:
                    hints_sent = True
                    if ui_hints:
                        yield encoder.encode(
                            CustomEvent(
                                type=EventType.CUSTOM, name="ui_hints", value=ui_hints
                            )
                        )
        except asyncio.CancelledError:
            # Cliente desconectou no meio do stream: aborta limpo (não emite RUN_ERROR)
            # e propaga o cancelamento para liberar o run subjacente.
            logger.info("Cliente desconectou durante a execução do agente; abortando.")
            raise
        except Exception as exc:  # resiliência: nenhuma exceção escapa do stream
            # Detalhe (tipo/1ª linha) só no log; cliente recebe mensagem genérica/segura.
            logger.error("Falha durante a execução do agente: %s", error_hint(exc))
            yield encoder.encode(
                RunErrorEvent(
                    type=EventType.RUN_ERROR,
                    message=describe_error(exc),
                    code="agent_run_error",
                )
            )

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())


@router.get(
    "/agent/health",
    response_model=AgentHealthResponse,
    summary="Liveness do agente",
)
def agent_health(request: Request) -> AgentHealthResponse:
    """Status do subsistema do agente, com o nome do agente ativo."""
    return AgentHealthResponse(agent=AgentInfo(name=get_agent(request).name))
