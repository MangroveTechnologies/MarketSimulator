"""Framework configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    data_dir: str = "/app/MarketSimulator/data"
    mangrove_data_dir: str = "/app/MangroveAI/data"
    signals_metadata_path: str = "/app/MangroveAI/domains/signals/signals_metadata.json"
    trading_defaults_path: str = "/app/MangroveAI/domains/ai_copilot/prompts/trading_defaults.json"
    chunk_size: int = 1024
    api_port: int = 5100

    class Config:
        env_prefix = "EXP_"


settings = Settings()
