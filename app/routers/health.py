"""Router de health check da aplicação."""

from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness do servidor")
def health() -> HealthResponse:
    """Retorna `{"status": "ok"}` se o servidor está no ar (liveness probe)."""
    return HealthResponse()
