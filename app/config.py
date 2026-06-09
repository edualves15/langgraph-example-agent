from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    # ── LLM ──────────────────────────────────────────────────────────────────────────────
    # O nome do provider é a ÚNICA chave de seleção; o mapeamento provider→classe/modelo vive
    # em `app/services/llm_service.py` (único ponto que lida com LLM). `url`/`api_key` servem
    # ao provider custom (e a quem precisar de base_url, como ollama/proxies).
    llm_provider: str = Field(
        "google", description="google | openai | anthropic | ollama | <qualquer outro = custom>.")
    llm_api_key: str = Field(
        "", validation_alias=AliasChoices("LLM_API_KEY", "GEMINI_API_KEY"),
        description="Chave do provider selecionado (vazia p/ ollama/local).")
    llm_base_url: str = Field(
        "", description="Base URL p/ ollama e p/ o provider custom (vazia nos providers cloud).")
    llm_temperature: float = Field(0.0, ge=0, description="Temperatura do modelo.")
    llm_tool_emulation: bool = Field(
        False, description="Liga a CAMADA de emulação (modelos sem tool calling/streaming nativo).")

    # ── AG-UI (protocolo/wire) — única var com o prefixo AG_UI_ ───────────────────────────
    ag_ui_stream_raw_events: bool = Field(
        True, description="Se False, omite eventos RAW do stream SSE do /stream.")

    # ── Aplicação/servidor (prefixo APP_) ────────────────────────────────────────────────
    app_cors_origins: str = Field(
        "*", description="Origens CORS permitidas (CSV). '*' libera todas.")
    app_max_body_bytes: int = Field(
        2_000_000, ge=0, description="Tamanho máx. do corpo (bytes); 0 desabilita.")
    app_mcp_startup_timeout: float = Field(
        15.0, ge=0, description="Timeout (s) por servidor MCP no startup; 0 desabilita.")
    app_enable_docs: bool = Field(
        True, description="Se False, desabilita /docs, /redoc e /openapi.json (produção).")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.app_cors_origins.split(",") if o.strip()]


settings = Settings()
