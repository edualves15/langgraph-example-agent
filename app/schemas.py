"""DTOs HTTP da camada de servidor (genéricos, sem domínio).

Modelos Pydantic das **respostas** da API, mantidos pequenos e explícitos para aparecerem
isolados na seção *Schemas* do Swagger — facilitando a quem consome a base recriar os
contratos no próprio cliente.

O **corpo** do `POST /agent` é o `RunAgentInput` oficial do protocolo AG-UI
(`ag_ui.core.types`) e por isso **não** é redefinido aqui (não reinventar o contrato oficial);
ele é validado em runtime e descrito em prosa no OpenAPI (ver `app/main.py`).
"""

from typing import Literal

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
