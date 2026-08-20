from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://forexai:forexai_secret@postgres:5432/forexai"
    DATABASE_URL_SYNC: str = "postgresql://forexai:forexai_secret@postgres:5432/forexai"
    REDIS_URL: str = "redis://redis:6379/0"
    # Redis caching
    REDIS_CACHE_ENABLED: bool = True
    REDIS_CACHE_TTL_S: int = 30

    # Auth
    JWT_SECRET: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: str = '["http://localhost:3000"]'

    # MT5 Connection
    MT5_ENABLED: bool = True
    MT5_PATH: str | None = None  # Auto-detect if None
    MT5_LOGIN: int | None = None  # Optional: account login
    MT5_PASSWORD: str | None = None  # Optional: account password
    MT5_SERVER: str | None = None  # Optional: broker server

    # Background Services
    TICK_COLLECTOR_ENABLED: bool = True
    CANDLE_SYNC_ENABLED: bool = True
    SESSION_DETECTOR_ENABLED: bool = True
    MARKET_STATUS_MONITOR_ENABLED: bool = True
    RECONNECTION_MANAGER_ENABLED: bool = True

    # Tick collection
    TICK_POLL_INTERVAL_MS: int = 500
    TICK_BATCH_SIZE: int = 50

    # Candle sync
    CANDLE_SYNC_INTERVAL_S: int = 30
    CANDLE_BACKFILL_COUNT: int = 200

    # Reconnection
    MT5_HEARTBEAT_INTERVAL_S: int = 10
    MT5_RECONNECT_INITIAL_BACKOFF_S: float = 1.0
    MT5_RECONNECT_MAX_BACKOFF_S: float = 60.0
    MT5_RECONNECT_MAX_RETRIES: int = 10

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
