from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8")

    app_env: str = "local"
    llm_provider: str = "gemini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    proprietary_base_url: str = ""
    proprietary_api_key: str = ""
    proprietary_model: str = ""

    mcp_enabled: bool = False
    mcp_servers_json: str = "{}"

    tavily_api_key: str = ""

    max_tool_calls: int = 10


settings = Settings()
