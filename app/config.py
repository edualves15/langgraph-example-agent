from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    tavily_api_key: str = ""


settings = Settings()
