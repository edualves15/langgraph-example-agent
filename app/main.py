from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.mcp.client import shutdown_mcp_client
from app.services.agent_service import AgentService

agent_service = AgentService()


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
async def chat(payload: ChatRequest) -> ChatResponse:
    answer = await agent_service.run(payload.message)
    return ChatResponse(answer=answer)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
