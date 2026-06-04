import logging
from collections.abc import AsyncIterator
from pathlib import Path

from ag_ui.core import EventType, RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.agent.graph import build_graph
from app.errors import describe_error

# Uvicorn configura apenas seus próprios loggers (uvicorn.*) e não toca no root.
# Sem isso, logger.info() de código da aplicação é silenciado (root em WARNING).
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s: %(name)s: %(message)s")

logger = logging.getLogger(__name__)

app = FastAPI(title="LangGraph Private Agent — AG-UI", version="0.2.0")

# ---------------------------------------------------------------------------
# Agente oficial AG-UI sobre LangGraph
# ---------------------------------------------------------------------------
# O LangGraphAgent mapeia os eventos do LangGraph para os eventos canônicos do
# protocolo AG-UI. O endpoint abaixo replica `add_langgraph_fastapi_endpoint`
# (mesmos primitivos oficiais: agent.run + EventEncoder), mas envolve o stream
# com tratamento de erros resiliente: nada vaza como traceback e toda falha é
# entregue ao cliente como um evento `RUN_ERROR` oficial.
graph = build_graph()
agent = LangGraphAgent(name="private-agent", graph=graph)

logger.info("Agente AG-UI inicializado.")


@app.post("/agent")
async def agent_endpoint(input_data: RunAgentInput, request: Request) -> StreamingResponse:
    encoder = EventEncoder(accept=request.headers.get("accept"))
    request_agent = agent.clone()  # estado isolado por requisição

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in request_agent.run(input_data):
                yield encoder.encode(event)
        except Exception as exc:  # resiliência: nenhuma exceção escapa do stream
            message = describe_error(exc)
            logger.error("Falha durante a execução do agente: %s", message)
            yield encoder.encode(
                RunErrorEvent(
                    type=EventType.RUN_ERROR,
                    message=message,
                    code="agent_run_error",
                )
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
