from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.services.agent_service import AgentService

app = FastAPI(title="LangGraph Private Agent", version="0.1.0")
agent_service = AgentService()


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
