"""Backtest API Router — run simulations, list/retrieve/delete past runs."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.repositories.candle_repository import CandleRepository
from app.repositories.indicator_repository import IndicatorRepository
from app.repositories.smc_repository import SMCRepository
from app.repositories.backtest_repository import BacktestRepository
from app.schemas.backtest import (
    BacktestRunRequest,
    BacktestResultResponse,
    BacktestRunSummary,
    BacktestRunListResponse,
    BacktestTradeResponse,
    BacktestDeleteResponse,
    EquityCurvePoint,
    MonthlyPerformanceItem,
)
from app.services.backtest_engine import BacktestEngine
from app.services.mt5_client import SUPPORTED_SYMBOLS
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])

TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


def _build_engine(db: AsyncSession) -> BacktestEngine:
    """Construct a BacktestEngine with real repositories."""
    return BacktestEngine(
        candle_repo=CandleRepository(db),
        indicator_repo=IndicatorRepository(db),
        smc_repo=SMCRepository(db),
        backtest_repo=BacktestRepository(db),
    )


# ── POST /run ────────────────────────────────────────────────────────────────────


@router.post("/run", response_model=BacktestResultResponse)
async def run_backtest(
    body: BacktestRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run a new backtest simulation.

    Walks through historical candles, simulates AI-driven trades with SL/TP logic,
    computes all performance metrics, and persists results to the database.
    """
    symbol = body.symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported. Supported: {SUPPORTED_SYMBOLS}",
        )
    if body.timeframe not in TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timeframe '{body.timeframe}'. Supported: {TIMEFRAMES}",
        )
    if body.start_date >= body.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be before end_date",
        )

    engine = _build_engine(db)
    try:
        result = await engine.run(
            symbol=symbol,
            timeframe=body.timeframe,
            start_date=body.start_date,
            end_date=body.end_date,
            initial_balance=body.initial_balance,
            risk_percentage=body.risk_percentage,
            user_id=str(current_user.id),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Backtest failed for %s/%s: %s", symbol, body.timeframe, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {str(e)}",
        )

    # Parse equity curve
    equity_curve = [
        EquityCurvePoint(timestamp=p["timestamp"], balance=p["balance"])
        for p in result.equity_curve
    ]

    # Parse monthly performance
    monthly_perf = [
        MonthlyPerformanceItem(
            month=m["month"],
            return_pct=m["return_pct"],
            trades=m["trades"],
            win_rate=m["win_rate"],
        )
        for m in result.monthly_performance
    ]

    # Build trade responses
    trade_responses = [
        BacktestTradeResponse(
            id="",  # populated from DB if needed; not returned in run response
            symbol=result.symbol,
            timeframe=result.timeframe,
            direction=t["direction"],
            entry_time=t["entry_time"],
            exit_time=t["exit_time"],
            entry_price=t["entry_price"],
            exit_price=t["exit_price"],
            position_size=t["position_size"],
            pnl=t["pnl"],
            pnl_pct=t["pnl_pct"],
            exit_reason=t["exit_reason"],
            created_at=result.end_date,
        )
        for t in result.trades
    ]

    return BacktestResultResponse(
        id=result.run_id or "",
        user_id=str(current_user.id),
        symbol=result.symbol,
        timeframe=result.timeframe,
        start_date=result.start_date,
        end_date=result.end_date,
        initial_balance=result.initial_balance,
        risk_percentage=result.risk_percentage,
        final_balance=result.final_balance,
        total_trades=result.total_trades,
        winning_trades=result.winning_trades,
        losing_trades=result.losing_trades,
        win_rate=result.win_rate,
        profit_factor=result.profit_factor,
        max_drawdown=result.max_drawdown,
        max_drawdown_amount=result.max_drawdown_amount,
        expectancy=result.expectancy,
        sharpe_ratio=result.sharpe_ratio,
        avg_win=result.avg_win,
        avg_loss=result.avg_loss,
        largest_win=result.largest_win,
        largest_loss=result.largest_loss,
        avg_hold_time=result.avg_hold_time,
        equity_curve=equity_curve,
        trades=trade_responses,
        monthly_performance=monthly_perf,
        created_at=result.end_date,
    )


# ── GET /runs ────────────────────────────────────────────────────────────────────


@router.get("/runs", response_model=BacktestRunListResponse)
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List past backtest runs for the current user (summaries only, no trades)."""
    repo = BacktestRepository(db)
    runs = await repo.get_runs_by_user(
        user_id=str(current_user.id),
        limit=limit,
        offset=offset,
    )

    summaries = [
        BacktestRunSummary(
            id=r.id,
            user_id=r.user_id,
            symbol=r.symbol,
            timeframe=r.timeframe,
            start_date=r.start_date,
            end_date=r.end_date,
            initial_balance=r.initial_balance,
            risk_percentage=r.risk_percentage,
            final_balance=r.final_balance,
            total_trades=r.total_trades,
            win_rate=r.win_rate,
            profit_factor=r.profit_factor,
            max_drawdown=r.max_drawdown,
            expectancy=r.expectancy,
            sharpe_ratio=r.sharpe_ratio,
            created_at=r.created_at,
        )
        for r in runs
    ]

    return BacktestRunListResponse(runs=summaries, count=len(summaries))


# ── GET /runs/{run_id} ───────────────────────────────────────────────────────────


@router.get("/runs/{run_id}", response_model=BacktestResultResponse)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full detail of a backtest run with trades and equity curve."""
    repo = BacktestRepository(db)
    run = await repo.get_run(run_id)

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest run '{run_id}' not found.",
        )

    if run.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this backtest run.",
        )

    trades = await repo.get_trades(run_id)

    # Parse stored JSON
    equity_curve_raw = []
    try:
        equity_curve_raw = json.loads(run.equity_curve)
    except (json.JSONDecodeError, TypeError):
        pass

    monthly_perf_raw = []
    try:
        monthly_perf_raw = json.loads(run.monthly_performance)
    except (json.JSONDecodeError, TypeError):
        pass

    # Compute derived metrics for the response
    trade_models = list(trades)
    winning = sum(1 for t in trade_models if t.pnl > 0)
    losing = sum(1 for t in trade_models if t.pnl <= 0)
    gross_profit = sum(t.pnl for t in trade_models if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trade_models if t.pnl <= 0))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else None
    avg_win = (gross_profit / winning) if winning > 0 else None
    avg_loss = -(gross_loss / losing) if losing > 0 else None
    largest_win = max((t.pnl for t in trade_models), default=None)
    largest_loss = min((t.pnl for t in trade_models), default=None)
    # avg hold time
    hold_times = [
        (t.exit_time - t.entry_time).total_seconds()
        for t in trade_models
        if t.exit_time > t.entry_time
    ]
    avg_hold = (sum(hold_times) / len(hold_times)) if hold_times else None
    max_dd_amount = 0.0
    if equity_curve_raw:
        peak = equity_curve_raw[0]["balance"]
        for p in equity_curve_raw:
            dd = peak - p["balance"]
            if dd > max_dd_amount:
                max_dd_amount = dd
            if p["balance"] > peak:
                peak = p["balance"]

    return BacktestResultResponse(
        id=run.id,
        user_id=run.user_id,
        symbol=run.symbol,
        timeframe=run.timeframe,
        start_date=run.start_date,
        end_date=run.end_date,
        initial_balance=run.initial_balance,
        risk_percentage=run.risk_percentage,
        final_balance=run.final_balance,
        total_trades=run.total_trades,
        winning_trades=winning,
        losing_trades=losing,
        win_rate=run.win_rate,
        profit_factor=pf if pf is not None else run.profit_factor,
        max_drawdown=run.max_drawdown,
        max_drawdown_amount=round(max_dd_amount, 2),
        expectancy=run.expectancy,
        sharpe_ratio=run.sharpe_ratio,
        avg_win=round(avg_win, 2) if avg_win is not None else None,
        avg_loss=round(avg_loss, 2) if avg_loss is not None else None,
        largest_win=round(largest_win, 2) if largest_win is not None else None,
        largest_loss=round(largest_loss, 2) if largest_loss is not None else None,
        avg_hold_time=round(avg_hold, 2) if avg_hold is not None else None,
        equity_curve=[
            EquityCurvePoint(timestamp=p["timestamp"], balance=p["balance"])
            for p in equity_curve_raw
        ],
        trades=[
            BacktestTradeResponse(
                id=t.id,
                symbol=t.symbol,
                timeframe=t.timeframe,
                direction=t.direction,
                entry_time=t.entry_time,
                exit_time=t.exit_time,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                position_size=t.position_size,
                pnl=t.pnl,
                pnl_pct=t.pnl_pct,
                exit_reason=t.exit_reason,
                created_at=t.created_at,
            )
            for t in trade_models
        ],
        monthly_performance=[
            MonthlyPerformanceItem(
                month=m["month"],
                return_pct=m["return_pct"],
                trades=m["trades"],
                win_rate=m["win_rate"],
            )
            for m in monthly_perf_raw
        ],
        created_at=run.created_at,
    )


# ── DELETE /runs/{run_id} ────────────────────────────────────────────────────────


@router.delete("/runs/{run_id}", response_model=BacktestDeleteResponse)
async def delete_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a backtest run and all its trades."""
    repo = BacktestRepository(db)

    # Verify ownership first
    run = await repo.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest run '{run_id}' not found.",
        )
    if run.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this backtest run.",
        )

    deleted = await repo.delete_run(run_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete backtest run.",
        )

    return BacktestDeleteResponse(message=f"Backtest run '{run_id}' deleted successfully.")
