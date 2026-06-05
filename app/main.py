import logging
from collections.abc import AsyncIterator
from pathlib import Path

from ag_ui.core import EventType, RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.agent.graph import build_graph
from app.config import settings
from app.errors import describe_error

# Uvicorn configura apenas seus próprios loggers (uvicorn.*) e não toca no root.
# Sem isso, logger.info() de código da aplicação é silenciado (root em WARNING).
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s: %(name)s: %(message)s")

logger = logging.getLogger(__name__)

app = FastAPI(title="LangGraph Private Agent — AG-UI", version="0.2.0")

# CORS — permite que QUALQUER frontend AG-UI (outra origem) consuma este agente, que é a
# proposta de desacoplamento do protocolo. Configurável por `AG_UI_CORS_ORIGINS`.
# Nota de conformidade: a spec proíbe wildcard "*" com `allow_credentials=True`; por isso
# credentials só são habilitadas quando as origens são explícitas (não "*").
_cors_origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials="*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Agente oficial AG-UI sobre LangGraph
# ---------------------------------------------------------------------------
# O endpoint abaixo replica `add_langgraph_fastapi_endpoint` com os **mesmos
# primitivos oficiais** (`agent.clone().run` + `EventEncoder`), mas envolve o stream
# num wrap fino de erro: em qualquer exceção, emite um `RUN_ERROR` — o evento
# **canônico** do protocolo para sinalizar falha (`ag_ui.core.RunErrorEvent`) — em vez
# de derrubar o SSE cru. É 100% protocolar; o helper puro apenas não oferece isso.
graph = build_graph()
agent = LangGraphAgent(name="private-agent", graph=graph)

logger.info("Agente AG-UI inicializado.")

# Eventos RAW são passthrough de callbacks internos do LangChain.
# Úteis para debugging, mas representam ~75%+ dos eventos no SSE.
# Quando desabilitados, apenas os eventos tipados do protocolo AG-UI são emitidos.
logger.info("AG_UI_STREAM_RAW_EVENTS=%s", settings.ag_ui_stream_raw_events)


@app.post("/agent")
async def agent_endpoint(input_data: RunAgentInput, request: Request) -> StreamingResponse:
    encoder = EventEncoder(accept=request.headers.get("accept"))
    request_agent = agent.clone()  # estado isolado por requisição (oficial)

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in request_agent.run(input_data):
                if not settings.ag_ui_stream_raw_events and event.type == EventType.RAW:
                    continue
                yield encoder.encode(event)
        except Exception as exc:  # resiliência: nenhuma exceção escapa do stream
            message = describe_error(exc)
            logger.error("Falha durante a execução do agente: %s", message)
            yield encoder.encode(
                RunErrorEvent(type=EventType.RUN_ERROR, message=message, code="agent_run_error")
            )

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())


@app.get("/agent/health")
def agent_health() -> dict:
    return {"status": "ok", "agent": {"name": agent.name}}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Handlers globais — capturam qualquer erro fora do stream, sem traceback.
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("Requisição inválida em %s: corpo não corresponde ao schema esperado.",
                   request.url.path)
    return JSONResponse(
        status_code=422,
        content={"detail": "Requisição inválida: o corpo não corresponde ao formato esperado."},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    message = describe_error(exc)
    logger.error("Erro não tratado em %s: %s", request.url.path, message)
    return JSONResponse(status_code=500, content={"detail": message})


# ---------------------------------------------------------------------------
# Página de demonstração (servida pelo próprio FastAPI)
# ---------------------------------------------------------------------------
# Montado por último para que /agent e /health tenham precedência.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
