from app.routers.auth import router as auth_router
from app.routers.market_data import router as market_data_router
from app.routers.indicators import router as indicators_router
from app.routers.smc import router as smc_router
from app.routers.ai import router as ai_router
from app.routers.risk import router as risk_router

__all__ = [
    "auth_router", "market_data_router", "indicators_router",
    "smc_router", "ai_router", "risk_router",
]
