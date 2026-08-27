from pydantic_settings import BaseSettings
from typing import List
import json

PLACEHOLDER_JWT_SECRET = "dev-secret-key-change-in-production"
MIN_PRODUCTION_SECRET_LENGTH = 32
PRODUCTION_ENVS = {"production", "prod"}


class Settings(BaseSettings):
    # Application environment: "development" (default) or "production" / "prod".
    # In production the app refuses to start unless a real JWT_SECRET is set.
    APP_ENV: str = "development"
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://forexai:forexai_secret@postgres:5432/forexai"
    DATABASE_URL_SYNC: str = "postgresql://forexai:forexai_secret@postgres:5432/forexai"
    REDIS_URL: str = "redis://redis:6379/0"
    # Redis caching
    REDIS_CACHE_ENABLED: bool = True
    REDIS_CACHE_TTL_S: int = 30
    # Auth
    JWT_SECRET: str = PLACEHOLDER_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: str = '["http://localhost:3000"]'
    # Auth rate limiting (per-minute buckets; see app/utils/ratelimit.py)
    AUTH_LOGIN_RATE_LIMIT: int = 20        # attempts per window per IP + per account
    AUTH_REGISTER_RATE_LIMIT: int = 10     # registrations per window per IP + per email
    AUTH_REFRESH_RATE_LIMIT: int = 60      # refreshes per window per IP
    AUTH_RATE_LIMIT_WINDOW_SECONDS: float = 60.0
    # MT5 Connection
    MT5_ENABLED: bool = True
    MT5_PATH: str | None = None  # Auto-detect if None
    MT5_LOGIN: int | None = None  # Optional: account login
    MT5_PASSWORD: str | None = None  # Optional: account password
    MT5_SERVER: str | None = None  # Optional: broker server
    # Market Data Provider (pluggable source)
    #   auto (default) -> OANDA if creds present, else MT5 path if MT5_ENABLED,
    #                     else mock; "oanda" | "mt5" | "mock" pick explicitly.
    MARKET_DATA_PROVIDER: str = "auto"
    # OANDA practice-style REST feed (env-driven only; no secrets committed).
    # When OANDA_API_KEY/OANDA_ACCOUNT_ID are absent the factory degrades to mock.
    OANDA_API_KEY: str | None = None
    OANDA_ACCOUNT_ID: str | None = None
    OANDA_ENV: str = "practice"  # practice|live (demo vs production account)
    OANDA_BASE_URL: str | None = None  # overrides host from OANDA_ENV when set
    OANDA_TIMEOUT_S: float = 10.0
    OANDA_REQUEST_DELAY_S: float = 0.0  # optional rate-limit sleep between calls
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

    def model_post_init(self, __context) -> None:
        """Fail-fast security guard:
        - In production require a real, non-placeholder JWT_SECRET.
        - CORS must be an explicit allow-list (no '*', never empty).
        Raises ValueError so ``settings = Settings()`` (and therefore app import)
        fails with a clear message instead of silently running insecure defaults.
        """
        env = (self.APP_ENV or "").strip().lower()
        if env in PRODUCTION_ENVS:
            secret = (self.JWT_SECRET or "").strip()
            if not secret:
                raise ValueError(
                    "JWT_SECRET is required in production (APP_ENV=production) but is "
                    "missing/empty. Set a strong random secret via the JWT_SECRET env var."
                )
            if secret == PLACEHOLDER_JWT_SECRET:
                raise ValueError(
                    "JWT_SECRET is still the development placeholder "
                    f"({PLACEHOLDER_JWT_SECRET!r}) in production. This is not a real "
                    "secret. Set a unique, random JWT_SECRET before starting in production."
                )
            if len(secret) < MIN_PRODUCTION_SECRET_LENGTH:
                raise ValueError(
                    f"JWT_SECRET in production must be at least "
                    f"{MIN_PRODUCTION_SECRET_LENGTH} characters long."
                )
        # CORS: strict, explicit allow-list only. No wildcard, never empty.
        try:
            origins = json.loads(self.CORS_ORIGINS)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(
                "CORS_ORIGINS must be a JSON list of explicit origins "
                f'(e.g. \'["https://app.example.com"]\'). Got {self.CORS_ORIGINS!r}: {e}'
            )
        if not isinstance(origins, list) or not origins:
            raise ValueError("CORS_ORIGINS must be a non-empty JSON list of explicit origins.")
        if "*" in origins:
            raise ValueError(
                "Wildcard origin '*' is not allowed in CORS_ORIGINS. Credentials are "
                "enabled, so CORS must use an explicit allowed-origin allow-list only."
            )
        # Normalize: strip whitespace and trailing slashes; reject empties.
        cleaned: List[str] = []
        for origin in origins:
            if not isinstance(origin, str):
                raise ValueError(f"CORS_ORIGINS entries must be strings, got {origin!r}")
            origin = origin.strip().rstrip("/")
            if not origin:
                raise ValueError("CORS_ORIGINS contains an empty origin entry.")
            cleaned.append(origin)
        self.CORS_ORIGINS = json.dumps(cleaned)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
