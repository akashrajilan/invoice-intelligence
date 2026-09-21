from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Invoice Intelligence API"
    max_upload_size_mb: int = 10
    max_extracted_chars: int = 50_000
    database_path: str = "data/invoices.db"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = 20.0
    allowed_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
