"""Market Data API Router — exposes market data endpoints.

All endpoints require authentication (via get_current_user dependency).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.symbol_repository import SymbolRepository
from app.repositories.candle_repository import CandleRepository
from app.repositories.tick_repository import TickRepository
from app.repositories.account_repository import AccountRepository
from app.repositories.broker_repository import BrokerRepository
from app.repositories.market_status_repository import MarketStatusRepository
from app.schemas.market_data import (
    SymbolResponse,
    SymbolListResponse,
    CandleResponse,
    CandleListResponse,
    TickResponse,
    TickListResponse,
    PriceResponse,
    AccountResponse,
    BrokerResponse,
    MarketStatusResponse,
    MarketStatusListResponse,
)
from app.utils.dependencies import get_current_user
from app.services.market_data_provider import get_market_data_provider, MarketDataProvider
from app.services.mt5_client import SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["market-data"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_provider() -> MarketDataProvider:
    """Get the current market-data provider with error handling."""
    try:
        return get_market_data_provider()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Market data service unavailable: {e}",
        )


# ── Symbols ───────────────────────────────────────────────────────────────────

@router.get("/symbols", response_model=SymbolListResponse)
async def list_symbols(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all supported symbols with metadata."""
    repo = SymbolRepository(db)
    symbols = await repo.get_all()
    return SymbolListResponse(
        symbols=[SymbolResponse.model_validate(s) for s in symbols],
        count=len(symbols),
    )


# ── Account ───────────────────────────────────────────────────────────────────

@router.get("/account", response_model=AccountResponse)
async def get_account(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get current MT5 account information."""
    repo = AccountRepository(db)
    account = await repo.get_latest()

    if account is None:
        # Try to fetch from MT5 live
        provider = _get_provider()
        if await provider.is_connected():
            try:
                acct_data = await provider.get_account_info()
                account = await repo.upsert_account(
                    balance=acct_data.balance,
                    equity=acct_data.equity,
                    margin=acct_data.margin,
                    free_margin=acct_data.free_margin,
                    leverage=acct_data.leverage,
                    currency=acct_data.currency,
                    name=acct_data.name,
                    server=acct_data.server,
                    login=acct_data.login,
                )
                await db.commit()
            except Exception as e:
                logger.error(f"Failed to fetch live account info: {e}")

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No account information available. Connect MT5 first.",
        )

    return AccountResponse.model_validate(account)


# ── Broker ────────────────────────────────────────────────────────────────────

@router.get("/broker", response_model=BrokerResponse)
async def get_broker(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get broker information from the connected MT5 terminal."""
    repo = BrokerRepository(db)
    broker = await repo.get_latest()

    if broker is None:
        provider = _get_provider()
        if await provider.is_connected():
            try:
                broker_data = await provider.get_broker_info()
                broker = await repo.upsert_broker(
                    name=broker_data.name,
                    server=broker_data.server,
                    timezone=broker_data.timezone,
                    regulation=broker_data.regulation,
                )
                await db.commit()
            except Exception as e:
                logger.error(f"Failed to fetch live broker info: {e}")

    if broker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No broker information available. Connect MT5 first.",
        )

    return BrokerResponse.model_validate(broker)


# ── Price ─────────────────────────────────────────────────────────────────────

@router.get("/price/{symbol}", response_model=PriceResponse)
async def get_price(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get latest tick price (bid/ask/spread) for a symbol."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported. Supported: {SUPPORTED_SYMBOLS}",
        )

    tick_repo = TickRepository(db)
    latest = await tick_repo.get_latest_tick(symbol)

    if latest is None:
        # Try live MT5
        provider = _get_provider()
        if await provider.is_connected():
            try:
                get_current = getattr(provider, "get_current_tick", None)
                if callable(get_current):
                    tick_data = await get_current(symbol)
                    if tick_data:
                        return PriceResponse(
                            symbol=symbol,
                            bid=tick_data.bid,
                            ask=tick_data.ask,
                            spread=tick_data.spread,
                            timestamp=tick_data.timestamp,
                        )
            except Exception as e:
                logger.error(f"Failed to fetch live price for {symbol}: {e}")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No price data available for {symbol}. Ensure MT5 is connected.",
        )

    return PriceResponse(
        symbol=latest.symbol,
        bid=latest.bid,
        ask=latest.ask,
        spread=latest.spread,
        timestamp=latest.timestamp,
    )


# ── Candles ───────────────────────────────────────────────────────────────────

@router.get("/candles/{symbol}", response_model=CandleListResponse)
async def get_candles(
    symbol: str,
    timeframe: str = Query(default="M5", description="Timeframe: M1,M5,M15,M30,H1,H4,D1"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get OHLCV candles for a symbol."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported.",
        )
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Timeframe '{timeframe}' is not supported. Supported: {SUPPORTED_TIMEFRAMES}",
        )

    repo = CandleRepository(db)
    candles = await repo.get_candles(symbol, timeframe, limit=limit)

    if not candles:
        # Try fetching from MT5 live
        provider = _get_provider()
        if await provider.is_connected():
            try:
                mt5_candles = await provider.fetch_candles(symbol, timeframe, limit)
                if mt5_candles:
                    from app.models.candle import Candle
                    db_candles = [
                        Candle(
                            symbol=c.symbol, timeframe=c.timeframe,
                            timestamp=c.timestamp, open=c.open, high=c.high,
                            low=c.low, close=c.close, tick_volume=c.tick_volume,
                            real_volume=c.real_volume, spread=c.spread,
                        )
                        for c in mt5_candles
                    ]
                    await repo.upsert_candles(db_candles)
                    await db.commit()
                    candles = await repo.get_candles(symbol, timeframe, limit=limit)
            except Exception as e:
                logger.error(f"Failed to fetch live candles for {symbol}/{timeframe}: {e}")

    return CandleListResponse(
        candles=[CandleResponse.model_validate(c) for c in (candles or [])],
        symbol=symbol,
        timeframe=timeframe,
        count=len(candles) if candles else 0,
    )


# ── Ticks ─────────────────────────────────────────────────────────────────────

@router.get("/ticks/{symbol}", response_model=TickListResponse)
async def get_ticks(
    symbol: str,
    limit: int = Query(default=1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get recent ticks for a symbol."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported.",
        )

    repo = TickRepository(db)
    ticks = await repo.get_ticks(symbol, limit=limit)

    return TickListResponse(
        ticks=[TickResponse.model_validate(t) for t in ticks],
        symbol=symbol,
        count=len(ticks),
    )


# ── Market Status ─────────────────────────────────────────────────────────────

@router.get("/market-status", response_model=MarketStatusListResponse)
async def get_market_status_all(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get current market status for all symbols."""
    repo = MarketStatusRepository(db)
    statuses = await repo.get_all()
    return MarketStatusListResponse(
        statuses=[MarketStatusResponse.model_validate(s) for s in statuses],
        count=len(statuses),
    )


@router.get("/market-status/{symbol}", response_model=MarketStatusResponse)
async def get_market_status_symbol(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get market status for a specific symbol."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported.",
        )

    repo = MarketStatusRepository(db)
    market_status = await repo.get_by_symbol(symbol)

    if market_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No market status found for {symbol}",
        )

    return MarketStatusResponse.model_validate(market_status)
