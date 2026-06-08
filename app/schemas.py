"""DTOs HTTP da camada de servidor (genéricos, sem domínio).

Modelos Pydantic das **respostas** da API, mantidos pequenos e explícitos para aparecerem
isolados na seção *Schemas* do Swagger — facilitando a quem consome a base recriar os
contratos no próprio cliente.

O **corpo** das rotas do agente é o `RunAgentInput` oficial do protocolo AG-UI
(`ag_ui.core.types`) e por isso **não** é redefinido aqui (não reinventar o contrato oficial);
ele é validado em runtime e descrito em prosa no OpenAPI (ver `app/main.py`).
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Resposta de erro padrão — mensagem segura para o cliente (sem detalhes internos)."""

    detail: str = Field(..., description="Mensagem de erro legível e segura.")

    model_config = {
        "json_schema_extra": {"examples": [{"detail": "Requisição grande demais."}]}
    }


class HealthResponse(BaseModel):
    """Status de saúde do servidor."""

    status: Literal["ok"] = Field("ok", description='Indicador de saúde; "ok" quando responde.')

    model_config = {"json_schema_extra": {"examples": [{"status": "ok"}]}}


class AgentInfo(BaseModel):
    """Identificação do agente AG-UI ativo."""

    name: str = Field(..., description="Nome do agente registrado no servidor.")


class AgentHealthResponse(BaseModel):
    """Status de saúde do subsistema do agente, com a identificação do agente ativo."""

    status: Literal["ok"] = Field("ok", description="Indicador de saúde do subsistema do agente.")
    agent: AgentInfo = Field(..., description="Dados do agente ativo.")

    model_config = {
        "json_schema_extra": {"examples": [{"status": "ok", "agent": {"name": "private-agent"}}]}
    }


class AgentInvokeResponse(BaseModel):
    """Resultado final **agregado** de um run do agente (rota síncrona `POST /agent/invoke`).

    Contrapartida não-streaming do `POST /agent/stream` (SSE): roda o agente até o fim,
    agrega os eventos AG-UI e devolve um único corpo JSON — para consumidores que não
    implementam o loop de eventos (script, server-to-server, webhook).
    """

    threadId: str = Field(..., description="Identificador da thread (eco do input).")
    runId: str = Field(..., description="Identificador do run (eco do input).")
    content: str = Field(
        "",
        description=(
            "Texto final do assistente — a mensagem final do run (preâmbulos descartados). "
            "Pode conter um bloco ```suggestions``` cru (a extração de sugestões é feita no "
            "front, não aqui)."
        ),
    )
    state: dict = Field(
        default_factory=dict,
        description="Snapshot final do estado do agente, sem as chaves protocolares (messages/tools).",
    )
    interrupt: Any | None = Field(
        None,
        description=(
            "Valor (app-defined) do interrupt HITL se o run pausou aguardando aprovação; "
            "null caso contrário."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "threadId": "t1",
                    "runId": "r1",
                    "content": "Posso confirmar sua reserva para 4 pessoas às 20h?",
                    "state": {"reservation": {"party_size": 4, "time": "20:00"}},
                    "interrupt": None,
                }
            ]
        }
    }
