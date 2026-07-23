from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MATERIAL_", env_file=".env", extra="ignore")

    chat_model: str | None = None
    chat_base_url: str | None = None
    chat_api_key: str = "local"
    embedding_model: str | None = None
    embedding_api_url: str | None = None
    embedding_api_key: str = "local"
    embedding_dimension: int = 1024
    source_type: str = "ncc"
    source_url: str | None = None
    postgres_url: str | None = None
