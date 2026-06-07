"""Router do endpoint AG-UI (`/agent`) sobre LangGraph.

Replica os primitivos oficiais (`agent.clone().run(input)` + `EventEncoder`), mas com um
**wrap fino de erro**: em qualquer exceção, emite um `RUN_ERROR` (`code="agent_run_error"`)
— evento **canônico** do protocolo para falhas — em vez de derrubar o SSE cru. O agente vem
de `request.app.state.agent` (criado no lifespan, ver `app/main.py`).
"""

import logging
from collections.abc import AsyncIterator

from ag_ui.core import CustomEvent, EventType, RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.errors import describe_error, error_hint

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])


@router.post("/agent")
async def agent_endpoint(input_data: RunAgentInput, request: Request) -> StreamingResponse:
    encoder = EventEncoder(accept=request.headers.get("accept"))
    request_agent = request.app.state.agent.clone()  # estado isolado por requisição (oficial)
    # Dicas de apresentação do domínio (ícones/títulos do resumo), entregues ao front
    # genérico pelo canal oficial AG-UI (evento CUSTOM), logo após o RUN_STARTED — sem
    # canal HTTP paralelo. O front (web/app.js) trata `name="ui_hints"` genericamente.
    ui_hints = getattr(request.app.state, "ui_hints", None)

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


@router.get("/agent/health")
def agent_health(request: Request) -> dict:
    return {"status": "ok", "agent": {"name": request.app.state.agent.name}}
