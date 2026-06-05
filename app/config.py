from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    tavily_api_key: str = ""

    ag_ui_stream_raw_events: bool = True

    # Origens permitidas via CORS (separadas por vírgula). "*" libera todas.
    ag_ui_cors_origins: str = "*"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.ag_ui_cors_origins.split(",") if o.strip()]


settings = Settings()
