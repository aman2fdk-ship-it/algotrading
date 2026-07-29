"""Risk Management API Router — position sizing, margin, loss limits."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.repositories.risk_repository import RiskSettingsRepository
from app.schemas.risk import (
    PipValueItem,
    PipValuesResponse,
    RiskCalculateRequest,
    RiskCalculateResponse,
    RiskLimitsResponse,
    RiskLimitsUpdateRequest,
    RiskResetResponse,
    RiskStatusResponse,
)
from app.services.risk_calculator import (
    calculate_risk_metrics,
    get_all_pip_values,
    SUPPORTED_SYMBOLS,
)
from app.services.risk_settings_service import (
    RiskSettingsService,
    UpdateSettingsRequest,
)
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


# ── Calculate Endpoint ─────────────────────────────────────────────────────────


@router.post("/calculate", response_model=RiskCalculateResponse)
async def calculate_risk(
    body: RiskCalculateRequest,
    current_user: User = Depends(get_current_user),
):
    """Calculate position size, margin, profit targets, and risk metrics.

    Pure math — no database writes. All inputs are validated.
    """
    symbol = body.symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported. Supported: {SUPPORTED_SYMBOLS}",
        )

    try:
        result = calculate_risk_metrics(
            account_balance=body.account_balance,
            risk_percentage=body.risk_percentage,
            entry_price=body.entry_price,
            stop_loss=body.stop_loss,
            symbol=symbol,
            leverage=body.leverage,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return RiskCalculateResponse(
        symbol=result.symbol,
        account_balance=result.account_balance,
        risk_percentage=result.risk_percentage,
        entry_price=result.entry_price,
        stop_loss=result.stop_loss,
        leverage=result.leverage,
        position_size=result.position_size,
        risk_amount=result.risk_amount,
        stop_loss_pips=result.stop_loss_pips,
        lot_size=result.lot_size,
        mini_lots=result.mini_lots,
        micro_lots=result.micro_lots,
        required_margin=result.required_margin,
        take_profit_1=result.take_profit_1,
        take_profit_2=result.take_profit_2,
        potential_profit_tp1=result.potential_profit_tp1,
        potential_profit_tp2=result.potential_profit_tp2,
        risk_reward_ratio_tp1=result.risk_reward_ratio_tp1,
        risk_reward_ratio_tp2=result.risk_reward_ratio_tp2,
        pip_size=result.pip_size,
        pip_value=result.pip_value,
    )


# ── Pip Values ─────────────────────────────────────────────────────────────────


@router.get("/pip-values", response_model=PipValuesResponse)
async def get_pip_values(
    current_user: User = Depends(get_current_user),
):
    """Get pip size and value information for all supported symbols."""
    all_values = get_all_pip_values()
    symbols_list = [
        PipValueItem(
            symbol=sym,
            pip_size=info["pip_size"],
            pip_value_per_lot=info["pip_value_per_lot"],
        )
        for sym, info in all_values.items()
    ]
    return PipValuesResponse(symbols=symbols_list, count=len(symbols_list))


# ── Loss Limits ────────────────────────────────────────────────────────────────


def _build_risk_service(db: AsyncSession) -> RiskSettingsService:
    """Construct RiskSettingsService with its repository."""
    return RiskSettingsService(RiskSettingsRepository(db))


@router.get("/limits", response_model=RiskLimitsResponse)
async def get_limits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's loss limits and running loss counters."""
    service = _build_risk_service(db)
    settings = await service.get_settings(str(current_user.id))

    return RiskLimitsResponse(
        user_id=settings.user_id,
        max_daily_loss=settings.max_daily_loss,
        max_weekly_loss=settings.max_weekly_loss,
        max_daily_loss_pct=settings.max_daily_loss_pct,
        max_weekly_loss_pct=settings.max_weekly_loss_pct,
        current_daily_loss=settings.current_daily_loss,
        current_weekly_loss=settings.current_weekly_loss,
        last_daily_reset=settings.last_daily_reset,
        last_weekly_reset=settings.last_weekly_reset,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.put("/limits", response_model=RiskLimitsResponse)
async def update_limits(
    body: RiskLimitsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update loss limits. Only provided fields are changed."""
    service = _build_risk_service(db)
    updates = UpdateSettingsRequest(
        max_daily_loss=body.max_daily_loss,
        max_weekly_loss=body.max_weekly_loss,
        max_daily_loss_pct=body.max_daily_loss_pct,
        max_weekly_loss_pct=body.max_weekly_loss_pct,
    )
    settings = await service.update_settings(str(current_user.id), updates)

    return RiskLimitsResponse(
        user_id=settings.user_id,
        max_daily_loss=settings.max_daily_loss,
        max_weekly_loss=settings.max_weekly_loss,
        max_daily_loss_pct=settings.max_daily_loss_pct,
        max_weekly_loss_pct=settings.max_weekly_loss_pct,
        current_daily_loss=settings.current_daily_loss,
        current_weekly_loss=settings.current_weekly_loss,
        last_daily_reset=settings.last_daily_reset,
        last_weekly_reset=settings.last_weekly_reset,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.get("/status", response_model=RiskStatusResponse)
async def get_trading_status(
    account_balance: float | None = Query(
        None, gt=0, description="Current account balance for %-based limits"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if trading is allowed based on loss limits.

    Optionally provide account_balance to evaluate percentage-based limits.
    """
    service = _build_risk_service(db)

    if account_balance is not None:
        status_result = await service.check_limits_with_balance(
            str(current_user.id), account_balance
        )
    else:
        status_result = await service.check_limits(str(current_user.id))

    return RiskStatusResponse(
        trading_allowed=status_result.trading_allowed,
        daily_loss=status_result.daily_loss,
        weekly_loss=status_result.weekly_loss,
        max_daily_loss=status_result.max_daily_loss,
        max_weekly_loss=status_result.max_weekly_loss,
        max_daily_loss_pct=status_result.max_daily_loss_pct,
        max_weekly_loss_pct=status_result.max_weekly_loss_pct,
        daily_used_pct=status_result.daily_used_pct,
        weekly_used_pct=status_result.weekly_used_pct,
        reason=status_result.reason,
    )


@router.post("/reset", response_model=RiskResetResponse)
async def reset_limits(
    reset_daily: bool = Query(True, description="Reset daily loss counter"),
    reset_weekly: bool = Query(False, description="Reset weekly loss counter"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset daily and/or weekly loss counters."""
    service = _build_risk_service(db)
    settings = None

    if reset_daily:
        settings = await service.reset_daily(str(current_user.id))
    if reset_weekly:
        settings = await service.reset_weekly(str(current_user.id))

    if settings is None:
        settings = await service.get_settings(str(current_user.id))

    return RiskResetResponse(
        message="Loss counters reset successfully.",
        current_daily_loss=settings.current_daily_loss,
        current_weekly_loss=settings.current_weekly_loss,
    )
