"""SMC API Router — exposes Smart Money Concepts detection data."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.smc_repository import SMCRepository
from app.schemas.smc import (
    SMCStructureResponse,
    SMCListResponse,
    SMCOrderBlockResponse,
    SMCLiquidityResponse,
    SMCFVGResponse,
    SMCPremiumDiscountResponse,
)
from app.utils.dependencies import get_current_user
from app.services.mt5_client import SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["smc"])


def _validate_symbol_timeframe(symbol: str, timeframe: str) -> None:
    """Validate symbol and timeframe params, raising HTTPException on failure."""
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


# ── Main SMC endpoint ────────────────────────────────────────────────────────────

@router.get("/smc/{symbol}", response_model=SMCListResponse)
async def get_smc_structures(
    symbol: str,
    timeframe: str = Query(default="H1", description="Timeframe: M1,M5,M15,M30,H1,H4,D1"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all SMC structures for a symbol and timeframe."""
    _validate_symbol_timeframe(symbol, timeframe)

    repo = SMCRepository(db)
    structures = await repo.get_all(symbol, timeframe, limit=limit)

    return SMCListResponse(
        structures=[SMCStructureResponse.model_validate(s) for s in structures],
        symbol=symbol,
        timeframe=timeframe,
        count=len(structures),
    )


# ── Filter by type ───────────────────────────────────────────────────────────────

@router.get("/smc/{symbol}/type/{structure_type}", response_model=SMCListResponse)
async def get_smc_by_type(
    symbol: str,
    structure_type: str,
    timeframe: str = Query(default="H1"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get SMC structures filtered by type (bos, choch, order_block, fvg, etc.)."""
    _validate_symbol_timeframe(symbol, timeframe)

    valid_types = {
        "bos", "choch", "order_block", "fvg",
        "liquidity_sweep", "equal_highs", "equal_lows", "premium_discount",
    }
    if structure_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid structure_type '{structure_type}'. Valid: {sorted(valid_types)}",
        )

    repo = SMCRepository(db)
    structures = await repo.get_by_type(symbol, timeframe, structure_type, limit=limit)

    return SMCListResponse(
        structures=[SMCStructureResponse.model_validate(s) for s in structures],
        symbol=symbol,
        timeframe=timeframe,
        count=len(structures),
    )


# ── Order Blocks ─────────────────────────────────────────────────────────────────

@router.get("/smc/{symbol}/order-blocks", response_model=SMCOrderBlockResponse)
async def get_order_blocks(
    symbol: str,
    timeframe: str = Query(default="H1"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get order blocks for a symbol and timeframe."""
    _validate_symbol_timeframe(symbol, timeframe)

    repo = SMCRepository(db)
    structures = await repo.get_by_type(symbol, timeframe, "order_block", limit=limit)

    return SMCOrderBlockResponse(
        order_blocks=[SMCStructureResponse.model_validate(s) for s in structures],
        symbol=symbol,
        timeframe=timeframe,
        count=len(structures),
    )


# ── Liquidity Sweeps ─────────────────────────────────────────────────────────────

@router.get("/smc/{symbol}/liquidity", response_model=SMCLiquidityResponse)
async def get_liquidity_sweeps(
    symbol: str,
    timeframe: str = Query(default="H1"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get liquidity sweeps for a symbol and timeframe."""
    _validate_symbol_timeframe(symbol, timeframe)

    repo = SMCRepository(db)
    structures = await repo.get_by_type(symbol, timeframe, "liquidity_sweep", limit=limit)

    return SMCLiquidityResponse(
        liquidity_sweeps=[SMCStructureResponse.model_validate(s) for s in structures],
        symbol=symbol,
        timeframe=timeframe,
        count=len(structures),
    )


# ── Fair Value Gaps ──────────────────────────────────────────────────────────────

@router.get("/smc/{symbol}/fvg", response_model=SMCFVGResponse)
async def get_fair_value_gaps(
    symbol: str,
    timeframe: str = Query(default="H1"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get fair value gaps for a symbol and timeframe."""
    _validate_symbol_timeframe(symbol, timeframe)

    repo = SMCRepository(db)
    structures = await repo.get_by_type(symbol, timeframe, "fvg", limit=limit)

    return SMCFVGResponse(
        fair_value_gaps=[SMCStructureResponse.model_validate(s) for s in structures],
        symbol=symbol,
        timeframe=timeframe,
        count=len(structures),
    )


# ── Premium / Discount ───────────────────────────────────────────────────────────

@router.get("/smc/{symbol}/premium-discount", response_model=SMCPremiumDiscountResponse)
async def get_premium_discount(
    symbol: str,
    timeframe: str = Query(default="H1"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get current premium/discount zone assessment for a symbol."""
    _validate_symbol_timeframe(symbol, timeframe)

    repo = SMCRepository(db)
    structure = await repo.get_latest(symbol, timeframe, "premium_discount")

    if structure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No premium/discount data found for {symbol}/{timeframe}. "
            f"Ensure the SMC calculator is running and candles exist.",
        )

    # Parse details JSON
    details = {}
    if structure.details:
        try:
            details = json.loads(structure.details)
        except json.JSONDecodeError:
            pass

    return SMCPremiumDiscountResponse(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=structure.timestamp,
        zone_type=details.get("zone_type", "unknown"),
        current_price=structure.price_mid or 0,
        swing_high=details.get("swing_high", structure.price_high or 0),
        swing_low=details.get("swing_low", structure.price_low or 0),
        position_pct=details.get("position_pct", 0.5),
    )
