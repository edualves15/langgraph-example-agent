from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = Field("", description="Chave da API Gemini (obrigatória em runtime).")
    gemini_model: str = Field("gemini-3.1-flash-lite", description="Nome do modelo Gemini.")

    ag_ui_stream_raw_events: bool = Field(
        True, description="Se False, omite eventos RAW do stream SSE do /stream.")

    # Origens permitidas via CORS (separadas por vírgula). "*" libera todas.
    ag_ui_cors_origins: str = Field(
        "*", description="Origens CORS permitidas (CSV). '*' libera todas.")

    # Tamanho máximo do corpo de uma requisição (bytes). Protege contra POSTs gigantes
    # (DoS de memória). Default generoso; 0 desabilita o limite.
    ag_ui_max_body_bytes: int = Field(
        2_000_000, ge=0, description="Tamanho máx. do corpo (bytes); 0 desabilita.")

    # Documentação OpenAPI: config de APLICAÇÃO (não do protocolo AG-UI) — por isso SEM o
    # prefixo `AG_UI_`. Em produção, desabilitar /docs, /redoc e /openapi.json é prática
    # recomendada (reduz a superfície/exposição da API).
    app_enable_docs: bool = Field(
        True, description="Se False, desabilita /docs, /redoc e /openapi.json (produção).")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.ag_ui_cors_origins.split(",") if o.strip()]


settings = Settings()
