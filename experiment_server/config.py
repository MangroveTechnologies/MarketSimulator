"""Framework configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    data_dir: str = "/app/MarketSimulator/data"
    ohlcv_dir: str = "/app/MarketSimulator/data/ohlcv"
    signals_metadata_path: str = "/app/MarketSimulator/data/signals_metadata.json"
    trading_defaults_path: str = "/app/MarketSimulator/data/trading_defaults.json"
    chunk_size: int = 1024
    api_port: int = 5100

    model_config = {"env_prefix": "EXP_"}


settings = Settings()
