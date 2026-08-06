"""BacktestMetrics — pure functions for computing performance metrics from trade history.

All calculations are self-contained: input a list of trades, output numbers.
No database access, no async.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence


@dataclass
class TradeRecord:
    """Minimal trade record for metric calculation."""

    entry_time: datetime
    exit_time: datetime
    direction: str  # BUY or SELL
    entry_price: float
    exit_price: float
    position_size: float
    pnl: float
    exit_reason: str  # stop_loss, take_profit, end_of_data


@dataclass
class MonthlySnapshot:
    """Performance for one calendar month."""

    month: str  # "YYYY-MM"
    return_pct: float
    trades: int
    win_rate: float  # 0–100


@dataclass
class MetricsResult:
    """All computed backtest metrics."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # 0–100
    gross_profit: float
    gross_loss: float
    profit_factor: float | None  # inf if no losses
    expectancy: float
    avg_win: float | None
    avg_loss: float | None
    largest_win: float | None
    largest_loss: float | None
    avg_hold_time_seconds: float | None
    max_drawdown_pct: float
    max_drawdown_amount: float
    sharpe_ratio: float | None
    equity_curve: list[dict] = field(default_factory=list)
    monthly_performance: list[MonthlySnapshot] = field(default_factory=list)


def compute_metrics(
    trades: Sequence[TradeRecord],
    initial_balance: float,
) -> MetricsResult:
    """Compute all backtest performance metrics from a list of trades.

    Args:
        trades: List of closed trades in chronological order (by exit_time).
        initial_balance: Starting account balance.

    Returns:
        MetricsResult with all computed metrics.
    """
    if not trades:
        return _empty_result(initial_balance)

    # ── Basic counts ──────────────────────────────────────────────────────────
    total_trades = len(trades)
    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]
    winning_trades = len(winners)
    losing_trades = len(losers)
    win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

    # ── Profit / Loss ─────────────────────────────────────────────────────────
    gross_profit = sum(t.pnl for t in winners)
    gross_loss = abs(sum(t.pnl for t in losers))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # ── Expectancy ────────────────────────────────────────────────────────────
    expectancy = sum(t.pnl for t in trades) / total_trades if total_trades > 0 else 0.0

    # ── Avg win/loss ──────────────────────────────────────────────────────────
    avg_win = (gross_profit / winning_trades) if winning_trades > 0 else None
    avg_loss = -(gross_loss / losing_trades) if losing_trades > 0 else None
    largest_win = max((t.pnl for t in winners), default=None)
    largest_loss = min((t.pnl for t in losers), default=None)

    # ── Avg hold time ─────────────────────────────────────────────────────────
    hold_times = [
        (t.exit_time - t.entry_time).total_seconds()
        for t in trades
    ]
    avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else None

    # ── Equity curve ──────────────────────────────────────────────────────────
    equity_curve = _build_equity_curve(trades, initial_balance)

    # ── Drawdown ──────────────────────────────────────────────────────────────
    max_dd_pct, max_dd_amount = _compute_max_drawdown(equity_curve)

    # ── Sharpe ratio ──────────────────────────────────────────────────────────
    sharpe = _compute_sharpe(trades, initial_balance, avg_hold_time)

    # ── Monthly performance ───────────────────────────────────────────────────
    monthly = _compute_monthly_performance(trades, initial_balance)

    return MetricsResult(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=round(win_rate, 2),
        gross_profit=round(gross_profit, 2),
        gross_loss=round(gross_loss, 2),
        profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else None,
        expectancy=round(expectancy, 2),
        avg_win=round(avg_win, 2) if avg_win is not None else None,
        avg_loss=round(avg_loss, 2) if avg_loss is not None else None,
        largest_win=round(largest_win, 2) if largest_win is not None else None,
        largest_loss=round(largest_loss, 2) if largest_loss is not None else None,
        avg_hold_time_seconds=round(avg_hold_time, 2) if avg_hold_time is not None else None,
        max_drawdown_pct=round(max_dd_pct, 2),
        max_drawdown_amount=round(max_dd_amount, 2),
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        equity_curve=equity_curve,
        monthly_performance=monthly,
    )


def _build_equity_curve(
    trades: Sequence[TradeRecord],
    initial_balance: float,
) -> list[dict]:
    """Build equity curve: starts with initial balance, then balance after each trade closes."""
    curve: list[dict] = [{
        "timestamp": trades[0].entry_time.isoformat() if trades else "",
        "balance": round(initial_balance, 2),
    }]
    balance = initial_balance
    for t in trades:
        balance += t.pnl
        curve.append({
            "timestamp": t.exit_time.isoformat(),
            "balance": round(balance, 2),
        })
    return curve


def _compute_max_drawdown(
    equity_curve: list[dict],
) -> tuple[float, float]:
    """Compute max drawdown percentage and amount from equity curve.

    The equity curve must start with initial balance as its first point.

    Returns:
        (max_drawdown_pct, max_drawdown_amount)
    """
    if not equity_curve:
        return (0.0, 0.0)

    peak = equity_curve[0]["balance"]
    max_dd_pct = 0.0
    max_dd_amount = 0.0

    for point in equity_curve:
        balance = point["balance"]
        if balance > peak:
            peak = balance
        dd = peak - balance
        dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
        if dd > max_dd_amount:
            max_dd_amount = dd

    return (max_dd_pct, max_dd_amount)


def _compute_sharpe(
    trades: Sequence[TradeRecord],
    initial_balance: float,
    avg_hold_time_seconds: float | None,
) -> float | None:
    """Compute Sharpe ratio from per-trade returns.

    sharpe = mean(returns) / std(returns) * sqrt(annualization_factor)

    Annualization factor = 252 / avg_trades_per_day
    Where avg_trades_per_day = 1 / avg_hold_days (from avg_hold_time)
    """
    if len(trades) < 2 or initial_balance <= 0:
        return None

    # Per-trade returns as percentage
    returns = [t.pnl / initial_balance for t in trades]

    mean_ret = sum(returns) / len(returns)

    # Population std
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    std_ret = math.sqrt(variance)

    if std_ret == 0:
        return 0.0

    # Annualization: estimate number of trades per year
    if avg_hold_time_seconds and avg_hold_time_seconds > 0:
        avg_hold_days = avg_hold_time_seconds / 86400.0
        trades_per_year = 252.0 / avg_hold_days if avg_hold_days > 0 else 252.0
    else:
        # Default: assume all trades happen in one year
        trades_per_year = float(len(trades))

    annualization_factor = math.sqrt(trades_per_year)
    sharpe = (mean_ret / std_ret) * annualization_factor
    return sharpe


def _compute_monthly_performance(
    trades: Sequence[TradeRecord],
    initial_balance: float,
) -> list[MonthlySnapshot]:
    """Group trades by month and compute per-month metrics."""
    if not trades:
        return []

    # Group trades by month
    months: dict[str, list[TradeRecord]] = {}
    for t in trades:
        month_key = t.exit_time.strftime("%Y-%m")
        months.setdefault(month_key, []).append(t)

    # Compute balance at start of each month
    # We need to compute cumulative pnl up to each month
    all_trades_sorted = sorted(trades, key=lambda t: t.exit_time)

    snapshots: list[MonthlySnapshot] = []
    running_balance = initial_balance

    for month_key in sorted(months.keys()):
        month_trades = months[month_key]
        # Compute balance at start of this month
        month_start_balance = running_balance

        month_pnl = sum(t.pnl for t in month_trades)
        month_return_pct = (
            (month_pnl / month_start_balance * 100.0)
            if month_start_balance > 0
            else 0.0
        )
        month_winners = sum(1 for t in month_trades if t.pnl > 0)
        month_win_rate = (
            (month_winners / len(month_trades) * 100.0)
            if month_trades
            else 0.0
        )

        snapshots.append(MonthlySnapshot(
            month=month_key,
            return_pct=round(month_return_pct, 2),
            trades=len(month_trades),
            win_rate=round(month_win_rate, 2),
        ))

        running_balance += month_pnl

    return snapshots


def _empty_result(initial_balance: float) -> MetricsResult:
    """Return a zero-trade metrics result."""
    return MetricsResult(
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate=0.0,
        gross_profit=0.0,
        gross_loss=0.0,
        profit_factor=None,
        expectancy=0.0,
        avg_win=None,
        avg_loss=None,
        largest_win=None,
        largest_loss=None,
        avg_hold_time_seconds=None,
        max_drawdown_pct=0.0,
        max_drawdown_amount=0.0,
        sharpe_ratio=None,
        equity_curve=[],
        monthly_performance=[],
    )
