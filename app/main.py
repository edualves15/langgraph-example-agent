import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

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


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    answer: str


@app.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    service: AgentService = Depends(get_agent_service),
) -> ChatResponse:
    try:
        answer = await service.run(payload.message)
        return ChatResponse(answer=answer)
    except Exception:
        logger.exception("Erro ao processar /chat")
        raise HTTPException(
            status_code=500, detail="Erro interno ao processar a mensagem.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
