import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import engine, Base
from app.routers import auth_router, market_data_router, indicators_router, smc_router, ai_router, risk_router, backtest_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global service references (for startup/shutdown) ──────────────────────────

_background_tasks: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup and start background services."""
    logger.info("Starting ForexAI Terminal backend (Module 2: Market Data Engine)...")

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured.")

    # Seed symbols
    await _seed_symbols()

    # Connect the market-data provider (mock fallback when nothing configured)
    provider = None
    from app.services.market_data_provider import get_market_data_provider
    provider = get_market_data_provider()
    try:
        connected = await provider.connect(
            path=settings.MT5_PATH,
            login=settings.MT5_LOGIN,
            password=settings.MT5_PASSWORD,
            server=settings.MT5_SERVER,
        )
        if connected:
            logger.info("Market data provider connected successfully")
        else:
            logger.warning("Market data provider connection failed — background services will retry")
    except Exception as e:
        logger.error(f"Market data provider connection error: {e}")

    # Start background services
    await _start_background_services(provider)

    yield

    # Shutdown
    await _stop_background_services()
    if provider:
        try:
            await provider.disconnect()
        except Exception:
            pass
    await engine.dispose()
    logger.info("Backend shutdown complete.")


async def _seed_symbols() -> None:
    """Seed the symbols table with the 10 supported symbols."""
    from app.database import async_session
    from app.repositories.symbol_repository import SymbolRepository
    from app.models.symbol import Symbol
    from app.services.mt5_client import SUPPORTED_SYMBOLS

    symbol_metadata = {
        "EURUSD": {"name": "Euro / US Dollar", "asset_type": "forex", "pip_size": 0.0001, "digits": 5},
        "GBPUSD": {"name": "British Pound / US Dollar", "asset_type": "forex", "pip_size": 0.0001, "digits": 5},
        "USDJPY": {"name": "US Dollar / Japanese Yen", "asset_type": "forex", "pip_size": 0.01, "digits": 3},
        "AUDUSD": {"name": "Australian Dollar / US Dollar", "asset_type": "forex", "pip_size": 0.0001, "digits": 5},
        "NZDUSD": {"name": "New Zealand Dollar / US Dollar", "asset_type": "forex", "pip_size": 0.0001, "digits": 5},
        "USDCAD": {"name": "US Dollar / Canadian Dollar", "asset_type": "forex", "pip_size": 0.0001, "digits": 5},
        "USDCHF": {"name": "US Dollar / Swiss Franc", "asset_type": "forex", "pip_size": 0.0001, "digits": 5},
        "XAUUSD": {"name": "Gold / US Dollar", "asset_type": "commodity", "pip_size": 0.01, "digits": 2},
        "BTCUSD": {"name": "Bitcoin / US Dollar", "asset_type": "crypto", "pip_size": 1.0, "digits": 2},
        "ETHUSD": {"name": "Ethereum / US Dollar", "asset_type": "crypto", "pip_size": 0.01, "digits": 2},
    }

    async with async_session() as session:
        repo = SymbolRepository(session)
        for code in SUPPORTED_SYMBOLS:
            meta = symbol_metadata.get(code, {"name": code, "asset_type": "forex", "pip_size": 0.0001, "digits": 5})
            symbol = Symbol(
                code=code,
                name=meta["name"],
                asset_type=meta["asset_type"],
                pip_size=meta["pip_size"],
                digits=meta["digits"],
                enabled=True,
            )
            await repo.upsert(symbol)
        await session.commit()
    logger.info(f"Seeded {len(SUPPORTED_SYMBOLS)} symbols")


async def _start_background_services(mt5_client) -> None:
    """Start all enabled background services."""
    global _background_tasks

    if settings.TICK_COLLECTOR_ENABLED and mt5_client:
        from app.services.tick_collector import LiveTickCollector
        tick_collector = LiveTickCollector(mt5_client)
        await tick_collector.start()
        _background_tasks.append(tick_collector)
        logger.info("Tick collector started")

    if settings.CANDLE_SYNC_ENABLED and mt5_client:
        from app.services.candle_sync import CandleSynchronizer
        candle_sync = CandleSynchronizer(mt5_client)
        await candle_sync.start()
        _background_tasks.append(candle_sync)
        logger.info("Candle synchronizer started")

    if settings.SESSION_DETECTOR_ENABLED:
        from app.services.session_detector import SessionDetector
        session_detector = SessionDetector()
        await session_detector.start()
        _background_tasks.append(session_detector)
        logger.info("Session detector started")

    if settings.MARKET_STATUS_MONITOR_ENABLED and mt5_client:
        from app.services.market_status import MarketStatusMonitor
        market_monitor = MarketStatusMonitor(mt5_client)
        await market_monitor.start()
        _background_tasks.append(market_monitor)
        logger.info("Market status monitor started")

    if settings.RECONNECTION_MANAGER_ENABLED and mt5_client:
        from app.services.reconnection import ReconnectionManager
        reconnection = ReconnectionManager(
            mt5_client,
            heartbeat_interval=settings.MT5_HEARTBEAT_INTERVAL_S,
            initial_backoff=settings.MT5_RECONNECT_INITIAL_BACKOFF_S,
            max_backoff=settings.MT5_RECONNECT_MAX_BACKOFF_S,
            max_retries=settings.MT5_RECONNECT_MAX_RETRIES,
        )
        await reconnection.start()
        _background_tasks.append(reconnection)
        logger.info("Reconnection manager started")

    # Start indicator calculator (always enabled when candle sync is enabled)
    if settings.CANDLE_SYNC_ENABLED:
        from app.services.indicator_calculator import IndicatorCalculatorService
        indicator_calc = IndicatorCalculatorService()
        await indicator_calc.start()
        _background_tasks.append(indicator_calc)
        logger.info("Indicator calculator started")

    # Start SMC calculator (always enabled when candle sync is enabled)
    if settings.CANDLE_SYNC_ENABLED:
        from app.services.smc_calculator import SMCCalculatorService
        smc_calc = SMCCalculatorService()
        await smc_calc.start()
        _background_tasks.append(smc_calc)
        logger.info("SMC calculator started")


async def _stop_background_services() -> None:
    """Stop all background services gracefully."""
    global _background_tasks
    for task in reversed(_background_tasks):
        try:
            if hasattr(task, "stop"):
                await task.stop()
        except Exception as e:
            logger.error(f"Error stopping background service: {e}")
    _background_tasks.clear()
    logger.info("All background services stopped")


# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="ForexAI Terminal API",
    description="Institutional-grade forex analysis terminal backend",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(market_data_router)
app.include_router(indicators_router)
app.include_router(smc_router)
app.include_router(ai_router)
app.include_router(risk_router)
app.include_router(backtest_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "forexai-terminal-backend", "version": "0.2.0"}
