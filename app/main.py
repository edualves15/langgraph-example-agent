import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.exceptions import AgentRuntimeError, ProviderAuthError, QuotaExceededError
from app.mcp.client import shutdown_mcp_client
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)

agent_service = AgentService()


def get_agent_service() -> AgentService:
    return agent_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await agent_service.warmup()
    yield
    await shutdown_mcp_client()


app = FastAPI(title="LangGraph Private Agent",
              version="0.1.0", lifespan=lifespan)


@app.exception_handler(QuotaExceededError)
async def quota_handler(request: Request, exc: QuotaExceededError) -> JSONResponse:
    logger.warning("Cota da API excedida.")
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Serviço temporariamente indisponível. Tente novamente em breve."},
    )


@app.exception_handler(ProviderAuthError)
async def auth_handler(request: Request, exc: ProviderAuthError) -> JSONResponse:
    logger.error("Credencial do provider inválida.")
    return JSONResponse(
        status_code=502,
        content={"detail": "Erro de configuração do serviço."},
    )


@app.exception_handler(AgentRuntimeError)
async def runtime_handler(request: Request, exc: AgentRuntimeError) -> JSONResponse:
    logger.exception("Erro de execução do agente.")
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno ao processar a mensagem."},
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    answer: str


@app.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    service: AgentService = Depends(get_agent_service),
) -> ChatResponse:
    answer = await service.run(payload.message)
    return ChatResponse(answer=answer)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
