"""Technical Indicators API Router — exposes calculated indicator data."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.indicator_repository import IndicatorRepository
from app.schemas.indicators import (
    IndicatorResponse,
    IndicatorListResponse,
    IndicatorLatestResponse,
    SupportResistanceResponse,
    FibonacciResponse,
)
from app.utils.dependencies import get_current_user
from app.services.mt5_client import SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["indicators"])


# ── Indicators ─────────────────────────────────────────────────────────────────

@router.get("/indicators/{symbol}", response_model=IndicatorListResponse)
async def get_indicators(
    symbol: str,
    timeframe: str = Query(default="H1", description="Timeframe: M1,M5,M15,M30,H1,H4,D1"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get latest technical indicator values for a symbol and timeframe."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported. Supported: {SUPPORTED_SYMBOLS}",
        )
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Timeframe '{timeframe}' is not supported. Supported: {SUPPORTED_TIMEFRAMES}",
        )

    repo = IndicatorRepository(db)
    indicators = await repo.get_by_symbol_timeframe(symbol, timeframe, limit=limit)

    return IndicatorListResponse(
        indicators=[IndicatorResponse.model_validate(i) for i in indicators],
        symbol=symbol,
        timeframe=timeframe,
        count=len(indicators),
    )


@router.get("/indicators/{symbol}/latest", response_model=IndicatorLatestResponse)
async def get_latest_indicator(
    symbol: str,
    timeframe: str = Query(default="H1"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the single latest indicator snapshot for a symbol and timeframe."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported.",
        )
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Timeframe '{timeframe}' is not supported.",
        )

    repo = IndicatorRepository(db)
    indicator = await repo.get_latest(symbol, timeframe)

    if indicator is None:
        # Valid symbol+timeframe with no rows yet is a healthy "no data" state,
        # not an error: the indicator calculator may not have processed this
        # timeframe yet. Return 200 with a null indicator so the UI can render
        # an empty state instead of a 404 storm.
        return IndicatorLatestResponse(indicator=None)

    return IndicatorLatestResponse(
        indicator=IndicatorResponse.model_validate(indicator)
    )


@router.get(
    "/support-resistance/{symbol}", response_model=SupportResistanceResponse
)
async def get_support_resistance(
    symbol: str,
    timeframe: str = Query(default="H1"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get support and resistance levels for a symbol and timeframe."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported.",
        )
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Timeframe '{timeframe}' is not supported.",
        )

    repo = IndicatorRepository(db)
    indicator = await repo.get_latest(symbol, timeframe)

    if indicator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No indicator data found for {symbol}/{timeframe}.",
        )

    return SupportResistanceResponse(
        symbol=indicator.symbol,
        timeframe=indicator.timeframe,
        timestamp=indicator.timestamp,
        support_levels=indicator.support_levels or [],
        resistance_levels=indicator.resistance_levels or [],
    )


@router.get("/fibonacci/{symbol}", response_model=FibonacciResponse)
async def get_fibonacci(
    symbol: str,
    timeframe: str = Query(default="H1"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get Fibonacci retracement levels for a symbol and timeframe."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported.",
        )
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Timeframe '{timeframe}' is not supported.",
        )

    repo = IndicatorRepository(db)
    indicator = await repo.get_latest(symbol, timeframe)

    if indicator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No indicator data found for {symbol}/{timeframe}.",
        )

    if indicator.fib_236 is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Fibonacci data available for {symbol}/{timeframe}.",
        )

    return FibonacciResponse(
        symbol=indicator.symbol,
        timeframe=indicator.timeframe,
        timestamp=indicator.timestamp,
        fib_0=0.0,  # Not stored, not needed
        fib_236=indicator.fib_236,
        fib_382=indicator.fib_382,
        fib_500=indicator.fib_500,
        fib_618=indicator.fib_618,
        fib_786=indicator.fib_786,
        fib_1=0.0,  # Not stored, not needed
    )
