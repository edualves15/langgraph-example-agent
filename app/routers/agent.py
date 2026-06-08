"""Router dos endpoints AG-UI do agente sobre LangGraph.

Duas formas de consumir o mesmo agente:

- `POST /agent/stream` (SSE) — superfície **canônica** do protocolo: replica os primitivos
  oficiais (`agent.clone().run(input)` + `EventEncoder`), com um **wrap fino de erro** que,
  em qualquer exceção, emite um `RUN_ERROR` (`code="agent_run_error"`) em vez de derrubar o
  SSE cru. Streama campo a campo (texto token a token, estado, interrupt).
- `POST /agent/invoke` (JSON) — contrapartida **síncrona**: roda o agente até o fim, **agrega**
  os eventos AG-UI e devolve um único corpo JSON (`AgentInvokeResponse`) — para consumidores
  que não implementam o loop de eventos.

O agente vem de `request.app.state.agent` (criado no lifespan, ver `app/main.py`).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Annotated, cast

from ag_ui.core import CustomEvent, EventType, RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.errors import describe_error, error_hint
from app.schemas import AgentHealthResponse, AgentInfo, AgentInvokeResponse, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

# Chaves protocolares do estado, omitidas do snapshot público (espelha PROTOCOL_STATE_KEYS
# do front, web/app.js): `messages`/`tools` são transporte do protocolo, não estado de negócio.
_PROTOCOL_STATE_KEYS = frozenset({"messages", "tools"})


def get_agent(request: Request) -> LangGraphAgent:
    """Acesso **tipado** ao agente AG-UI guardado em `app.state` (criado no lifespan)."""
    return cast(LangGraphAgent, request.app.state.agent)


# Saída do agente (output) = stream SSE de eventos AG-UI. SSE não é modelável como um corpo
# único no OpenAPI, então é documentado como **catálogo de eventos** + referência ao protocolo
# (a definição tipada vive no pacote `ag-ui-protocol`). Erros usam o DTO ErrorResponse.
_AGENT_RESPONSES: dict = {
    200: {
        "description": (
            "Stream SSE (text/event-stream) de eventos AG-UI:\n"
            "- RUN_STARTED {threadId, runId} · RUN_FINISHED · RUN_ERROR {message, code}\n"
            "- TEXT_MESSAGE_START {messageId, role} · _CONTENT {delta} · _END\n"
            "- TOOL_CALL_START {toolCallId, toolCallName} · _ARGS {delta} · _END · _RESULT\n"
            "- STATE_SNAPSHOT {snapshot} · STATE_DELTA {delta JSON-Patch}\n"
            "- CUSTOM {name, value} (ex.: name=\"ui_hints\") · RAW (omitível via "
            "AG_UI_STREAM_RAW_EVENTS)\n\n"
            "Definições tipadas dos eventos: pacote `ag-ui-protocol` (`ag_ui.core`) e a spec "
            "do protocolo → https://docs.ag-ui.com"
        ),
        "content": {"text/event-stream": {}},
    },
    413: {"model": ErrorResponse, "description": "Corpo da requisição acima do limite."},
    422: {"model": ErrorResponse, "description": "Corpo inválido (não corresponde a RunAgentInput)."},
    500: {"model": ErrorResponse, "description": "Erro inesperado ao processar a requisição."},
}

# Exemplo de corpo (input) exibido no Swagger ("Try it out").
_AGENT_BODY_EXAMPLE = {
    "threadId": "t1",
    "runId": "r1",
    "state": {},
    "messages": [{"id": "m1", "role": "user", "content": "Olá"}],
    "tools": [],
    "context": [],
    "forwardedProps": {},
}


@router.post(
    "/agent/stream",
    summary="Executa o agente e transmite eventos AG-UI (SSE)",
    responses=_AGENT_RESPONSES,
)
async def agent_stream(
    input_data: Annotated[
        RunAgentInput,
        Body(openapi_examples={
            "minimo": {"summary": "Mensagem simples do usuário", "value": _AGENT_BODY_EXAMPLE},
        }),
    ],
    request: Request,
) -> StreamingResponse:
    """Roda o agente para um `RunAgentInput` (protocolo AG-UI) e devolve o resultado como
    um stream **SSE** de eventos AG-UI (ver respostas). O **input** é tipado pelo modelo
    oficial `RunAgentInput`; o **output** é o catálogo de eventos documentado no 200. Erros
    são emitidos como `RUN_ERROR` dentro do stream; falhas pré-stream usam `ErrorResponse`."""
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


_INVOKE_RESPONSES: dict = {
    413: {"model": ErrorResponse, "description": "Corpo da requisição acima do limite."},
    422: {"model": ErrorResponse, "description": "Corpo inválido (não corresponde a RunAgentInput)."},
    500: {"model": ErrorResponse, "description": "Erro inesperado ou RUN_ERROR durante o run."},
}


@router.post(
    "/agent/invoke",
    response_model=AgentInvokeResponse,
    responses=_INVOKE_RESPONSES,
    summary="Executa o agente e devolve o resultado final agregado (JSON)",
)
async def agent_invoke(
    input_data: Annotated[
        RunAgentInput,
        Body(openapi_examples={
            "minimo": {"summary": "Mensagem simples do usuário", "value": _AGENT_BODY_EXAMPLE},
        }),
    ],
    request: Request,
) -> AgentInvokeResponse:
    """Roda o agente para um `RunAgentInput` e devolve o **resultado final agregado** num
    único corpo JSON (`AgentInvokeResponse`) — contrapartida síncrona do `/agent/stream`.

    Agrega os eventos AG-UI do run: `content` = a **mensagem final** do assistente (cada
    novo `TEXT_MESSAGE_START` reinicia o acúmulo, convergindo para a última e descartando
    preâmbulos — espelha a regra de "uma bolha por run" do front); `state` = o último
    `STATE_SNAPSHOT` (sem chaves protocolares); `interrupt` = o `value` de um `CUSTOM`
    `on_interrupt` (HITL), ou `null`. Um `RUN_ERROR` ou qualquer exceção viram **500**
    (`ErrorResponse`), com a mensagem já saneada (`describe_error`)."""
    request_agent = get_agent(request).clone()  # estado isolado por requisição (oficial)

    content = ""
    state: dict = {}
    interrupt = None
    try:
        async for event in request_agent.run(input_data):
            if event.type == EventType.TEXT_MESSAGE_START:
                content = ""  # nova mensagem substitui preâmbulos (converge p/ a final)
            elif event.type == EventType.TEXT_MESSAGE_CONTENT:
                content += event.delta
            elif event.type == EventType.STATE_SNAPSHOT:
                state = event.snapshot or {}
            elif event.type == EventType.CUSTOM and event.name == "on_interrupt":
                interrupt = event.value
            elif event.type == EventType.RUN_ERROR:
                # RUN_ERROR é evento (não exceção): a lib o emite p/ erros do LangGraph.
                raise HTTPException(status_code=500, detail=event.message)
    except asyncio.CancelledError:
        # Cliente desconectou: aborta limpo e propaga p/ liberar o run subjacente.
        logger.info("Cliente desconectou durante a execução do agente; abortando.")
        raise
    except HTTPException:
        raise
    except Exception as exc:  # detalhe só no log; cliente recebe mensagem genérica/segura
        logger.error("Falha durante a execução do agente: %s", error_hint(exc))
        raise HTTPException(status_code=500, detail=describe_error(exc)) from exc

    public_state = {k: v for k, v in state.items() if k not in _PROTOCOL_STATE_KEYS}
    return AgentInvokeResponse(
        threadId=input_data.thread_id,
        runId=input_data.run_id,
        content=content,
        state=public_state,
        interrupt=interrupt,
    )


@router.get(
    "/agent/health",
    response_model=AgentHealthResponse,
    summary="Liveness do agente",
)
def agent_health(request: Request) -> AgentHealthResponse:
    """Status do subsistema do agente, com o nome do agente ativo."""
    return AgentHealthResponse(agent=AgentInfo(name=get_agent(request).name))
