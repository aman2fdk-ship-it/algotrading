"""Unit tests for BacktestEngine and BacktestMetrics — pure logic (no DB)."""

from __future__ import annotations

import math
import pytest
from datetime import datetime, timezone, timedelta

from app.services.backtest_metrics import (
    TradeRecord,
    compute_metrics,
    MetricsResult,
)
from app.services.backtest_engine import BacktestEngine, BacktestResult
from app.models.candle import Candle


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _make_candle(
    timestamp: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    """Create a Candle with minimal fields for testing."""
    return Candle(
        symbol="EURUSD",
        timeframe="H1",
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        tick_volume=100,
        real_volume=0,
        spread=0,
    )


def _make_trade(
    entry_time: datetime,
    exit_time: datetime,
    direction: str,
    entry_price: float,
    exit_price: float,
    position_size: float,
    pnl: float,
    exit_reason: str = "take_profit",
) -> TradeRecord:
    return TradeRecord(
        entry_time=entry_time,
        exit_time=exit_time,
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        position_size=position_size,
        pnl=pnl,
        exit_reason=exit_reason,
    )


# ═════════════════════════════════════════════════════════════════════════════════
# Exit Logic Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestExitLogic:
    """Tests for BacktestEngine._check_exit SL/TP detection."""

    def test_long_sl_hit_only(self):
        """Long: candle low crosses SL, high does not reach TP."""
        candle = _make_candle(
            datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            open_=1.1000, high=1.1020, low=1.0950, close=1.1010,
        )
        from app.services.backtest_engine import _OpenPosition
        pos = _OpenPosition(
            direction="BUY",
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=1.1000,
            stop_loss=1.0980,
            take_profit=1.1100,
            position_size=10000.0,
        )
        result = BacktestEngine._check_exit(candle, pos)
        assert result is not None
        assert result[0] == 1.0980  # exit at SL
        assert result[1] == "stop_loss"

    def test_long_tp_hit_only(self):
        """Long: candle high crosses TP, low does not hit SL."""
        candle = _make_candle(
            datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            open_=1.1000, high=1.1120, low=1.0990, close=1.1110,
        )
        from app.services.backtest_engine import _OpenPosition
        pos = _OpenPosition(
            direction="BUY",
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            position_size=10000.0,
        )
        result = BacktestEngine._check_exit(candle, pos)
        assert result is not None
        assert result[0] == 1.1100
        assert result[1] == "take_profit"

    def test_short_sl_hit_only(self):
        """Short: candle high crosses SL, low does not hit TP."""
        candle = _make_candle(
            datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            open_=1.1000, high=1.1030, low=1.0980, close=1.1020,
        )
        from app.services.backtest_engine import _OpenPosition
        pos = _OpenPosition(
            direction="SELL",
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=1.1000,
            stop_loss=1.1020,
            take_profit=1.0900,
            position_size=10000.0,
        )
        result = BacktestEngine._check_exit(candle, pos)
        assert result is not None
        assert result[0] == 1.1020
        assert result[1] == "stop_loss"

    def test_short_tp_hit_only(self):
        """Short: candle low crosses TP, high does not hit SL."""
        candle = _make_candle(
            datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            open_=1.1000, high=1.1010, low=1.0880, close=1.0890,
        )
        from app.services.backtest_engine import _OpenPosition
        pos = _OpenPosition(
            direction="SELL",
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=1.1000,
            stop_loss=1.1050,
            take_profit=1.0900,
            position_size=10000.0,
        )
        result = BacktestEngine._check_exit(candle, pos)
        assert result is not None
        assert result[0] == 1.0900
        assert result[1] == "take_profit"

    def test_both_hit_sl_closer_to_open__long(self):
        """Long: both SL and TP hit; SL is closer to open -> SL wins."""
        candle = _make_candle(
            datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            open_=1.1000, high=1.1150, low=1.0900, close=1.1050,
        )
        from app.services.backtest_engine import _OpenPosition
        pos = _OpenPosition(
            direction="BUY",
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=1.1000,
            stop_loss=1.0980,   # 0.002 from open
            take_profit=1.1120,  # 0.012 from open — SL is closer
            position_size=10000.0,
        )
        result = BacktestEngine._check_exit(candle, pos)
        assert result is not None
        assert result[0] == 1.0980
        assert result[1] == "stop_loss"

    def test_both_hit_tp_closer_to_open__long(self):
        """Long: both hit; TP is closer to open -> TP wins."""
        candle = _make_candle(
            datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            open_=1.1000, high=1.1150, low=1.0900, close=1.1050,
        )
        from app.services.backtest_engine import _OpenPosition
        pos = _OpenPosition(
            direction="BUY",
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=1.1000,
            stop_loss=1.0880,   # 0.012 from open
            take_profit=1.1020,  # 0.002 from open — TP is closer
            position_size=10000.0,
        )
        result = BacktestEngine._check_exit(candle, pos)
        assert result is not None
        assert result[0] == 1.1020
        assert result[1] == "take_profit"

    def test_both_hit_sl_closer_to_open__short(self):
        """Short: both hit; SL is closer to open -> SL wins."""
        candle = _make_candle(
            datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            open_=1.1000, high=1.1150, low=1.0850, close=1.0900,
        )
        from app.services.backtest_engine import _OpenPosition
        pos = _OpenPosition(
            direction="SELL",
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=1.1000,
            stop_loss=1.1020,    # 0.002 from open — SL closer
            take_profit=1.0880,  # 0.012 from open
            position_size=10000.0,
        )
        result = BacktestEngine._check_exit(candle, pos)
        assert result is not None
        assert result[0] == 1.1020
        assert result[1] == "stop_loss"

    def test_neither_hit(self):
        """No SL or TP hit — position stays open."""
        candle = _make_candle(
            datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            open_=1.1000, high=1.1010, low=1.0990, close=1.1005,
        )
        from app.services.backtest_engine import _OpenPosition
        pos = _OpenPosition(
            direction="BUY",
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            position_size=10000.0,
        )
        result = BacktestEngine._check_exit(candle, pos)
        assert result is None

    def test_sl_exactly_at_low__long(self):
        """Long: SL equals candle low exactly."""
        candle = _make_candle(
            datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
            open_=1.1000, high=1.1050, low=1.0980, close=1.1040,
        )
        from app.services.backtest_engine import _OpenPosition
        pos = _OpenPosition(
            direction="BUY",
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            entry_price=1.1000,
            stop_loss=1.0980,
            take_profit=1.1100,
            position_size=10000.0,
        )
        result = BacktestEngine._check_exit(candle, pos)
        assert result is not None
        assert result[0] == 1.0980
        assert result[1] == "stop_loss"


# ═════════════════════════════════════════════════════════════════════════════════
# P&L Calculation Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestPnL:
    """Tests for BacktestEngine._calc_pnl."""

    def test_long_profit(self):
        pnl = BacktestEngine._calc_pnl("BUY", 1.1000, 1.1100, 100000.0)
        # (1.1100 - 1.1000) / 1.1000 * 100000 = 0.00909... * 100000 = 909.09
        assert pnl == pytest.approx(909.09, rel=0.01)

    def test_long_loss(self):
        pnl = BacktestEngine._calc_pnl("BUY", 1.1000, 1.0900, 100000.0)
        # (1.0900 - 1.1000) / 1.1000 * 100000 = -0.00909 * 100000 = -909.09
        assert pnl == pytest.approx(-909.09, rel=0.01)

    def test_short_profit(self):
        pnl = BacktestEngine._calc_pnl("SELL", 1.1000, 1.0900, 100000.0)
        # (1.1000 - 1.0900) / 1.1000 * 100000 = 0.00909 * 100000 = 909.09
        assert pnl == pytest.approx(909.09, rel=0.01)

    def test_short_loss(self):
        pnl = BacktestEngine._calc_pnl("SELL", 1.1000, 1.1100, 100000.0)
        # (1.1000 - 1.1100) / 1.1000 * 100000 = -0.00909 * 100000 = -909.09
        assert pnl == pytest.approx(-909.09, rel=0.01)

    def test_zero_entry_price(self):
        pnl = BacktestEngine._calc_pnl("BUY", 0.0, 1.1000, 100000.0)
        assert pnl == 0.0

    def test_zero_position_size(self):
        pnl = BacktestEngine._calc_pnl("BUY", 1.1000, 1.1100, 0.0)
        assert pnl == 0.0


# ═════════════════════════════════════════════════════════════════════════════════
# Metrics Calculation Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestComputeMetrics:
    """Tests for compute_metrics with known trade arrays."""

    def test_empty_trades(self):
        result = compute_metrics([], 10000.0)
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.expectancy == 0.0
        assert result.equity_curve == []
        assert result.monthly_performance == []

    def test_single_winning_trade(self):
        t = _make_trade(
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 1, 14, 0, tzinfo=timezone.utc),
            direction="BUY",
            entry_price=1.1000,
            exit_price=1.1100,
            position_size=100000.0,
            pnl=909.09,
            exit_reason="take_profit",
        )
        result = compute_metrics([t], 10000.0)

        assert result.total_trades == 1
        assert result.winning_trades == 1
        assert result.losing_trades == 0
        assert result.win_rate == 100.0
        assert result.gross_profit == 909.09
        assert result.gross_loss == 0.0
        assert result.profit_factor is None  # inf -> None in our rounding
        assert result.expectancy == 909.09
        assert result.avg_win == 909.09
        assert result.avg_loss is None
        assert result.max_drawdown_pct == 0.0  # no drawdown with only winners
        assert len(result.equity_curve) == 2  # initial balance + 1 trade
        assert result.equity_curve[1]["balance"] == 10909.09

    def test_single_losing_trade(self):
        t = _make_trade(
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 1, 14, 0, tzinfo=timezone.utc),
            direction="BUY",
            entry_price=1.1000,
            exit_price=1.0900,
            position_size=100000.0,
            pnl=-909.09,
            exit_reason="stop_loss",
        )
        result = compute_metrics([t], 10000.0)

        assert result.total_trades == 1
        assert result.winning_trades == 0
        assert result.losing_trades == 1
        assert result.win_rate == 0.0
        assert result.gross_profit == 0.0
        assert result.gross_loss == 909.09
        assert result.profit_factor == 0.0
        assert result.expectancy == -909.09
        assert result.avg_win is None
        assert result.avg_loss == -909.09
        assert result.max_drawdown_pct > 0.0

    def test_mixed_trades_2w_1l(self):
        t1 = _make_trade(
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 1, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.1000, exit_price=1.1100,
            position_size=100000.0, pnl=909.09,
        )
        t2 = _make_trade(
            entry_time=datetime(2024, 6, 2, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 2, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.1100, exit_price=1.1300,
            position_size=100000.0, pnl=1801.80,
        )
        t3 = _make_trade(
            entry_time=datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 3, 14, 0, tzinfo=timezone.utc),
            direction="SELL", entry_price=1.1300, exit_price=1.1400,
            position_size=100000.0, pnl=-884.96,
            exit_reason="stop_loss",
        )
        result = compute_metrics([t1, t2, t3], 10000.0)

        assert result.total_trades == 3
        assert result.winning_trades == 2
        assert result.losing_trades == 1
        assert result.win_rate == pytest.approx(66.67, rel=0.01)
        assert result.gross_profit == pytest.approx(2710.89, rel=0.01)
        assert result.gross_loss == pytest.approx(884.96, rel=0.01)
        assert result.profit_factor == pytest.approx(2710.89 / 884.96, rel=0.01)
        assert result.expectancy == pytest.approx((909.09 + 1801.80 - 884.96) / 3, rel=0.01)
        assert result.avg_win == pytest.approx((909.09 + 1801.80) / 2, rel=0.01)
        assert result.avg_loss == pytest.approx(-884.96, rel=0.01)
        assert result.largest_win == 1801.80
        assert result.largest_loss == -884.96

    def test_equity_curve_sequence(self):
        t1 = _make_trade(
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 1, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.10, exit_price=1.11,
            position_size=100000.0, pnl=1000.0,
        )
        t2 = _make_trade(
            entry_time=datetime(2024, 6, 2, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 2, 14, 0, tzinfo=timezone.utc),
            direction="SELL", entry_price=1.11, exit_price=1.12,
            position_size=100000.0, pnl=-500.0,
            exit_reason="stop_loss",
        )
        result = compute_metrics([t1, t2], 10000.0)

        assert len(result.equity_curve) == 3  # initial balance + 2 trades
        assert result.equity_curve[0]["balance"] == 10000.0
        assert result.equity_curve[1]["balance"] == 11000.0
        assert result.equity_curve[2]["balance"] == 10500.0

    def test_max_drawdown(self):
        t1 = _make_trade(
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 1, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.10, exit_price=1.11,
            position_size=100000.0, pnl=1000.0,
        )
        t2 = _make_trade(
            entry_time=datetime(2024, 6, 2, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 2, 14, 0, tzinfo=timezone.utc),
            direction="SELL", entry_price=1.11, exit_price=1.12,
            position_size=100000.0, pnl=-1500.0,
            exit_reason="stop_loss",
        )
        t3 = _make_trade(
            entry_time=datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 3, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.12, exit_price=1.13,
            position_size=100000.0, pnl=800.0,
        )
        result = compute_metrics([t1, t2, t3], 10000.0)

        # Peak=11000, then 9500 (DD=1500/11000=13.64%), then 10300
        assert result.max_drawdown_pct == pytest.approx(13.64, rel=0.1)
        assert result.max_drawdown_amount == 1500.0

    def test_monthly_performance(self):
        t1 = _make_trade(
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.10, exit_price=1.11,
            position_size=100000.0, pnl=1000.0,
        )
        t2 = _make_trade(
            entry_time=datetime(2024, 7, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 7, 5, 14, 0, tzinfo=timezone.utc),
            direction="SELL", entry_price=1.11, exit_price=1.10,
            position_size=100000.0, pnl=900.0,
        )
        result = compute_metrics([t1, t2], 10000.0)

        assert len(result.monthly_performance) == 2
        months = {m.month for m in result.monthly_performance}
        assert months == {"2024-06", "2024-07"}

        june = next(m for m in result.monthly_performance if m.month == "2024-06")
        assert june.trades == 1
        assert june.return_pct == 10.0  # 1000/10000 * 100

        july = next(m for m in result.monthly_performance if m.month == "2024-07")
        assert july.trades == 1
        # July starts at 11000 balance, earns 900 -> 900/11000*100 ≈ 8.18%
        assert july.return_pct == pytest.approx(8.18, rel=0.1)

    def test_sharpe_nonzero(self):
        """With varied returns, Sharpe should be computable."""
        t1 = _make_trade(
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 1, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.10, exit_price=1.11,
            position_size=100000.0, pnl=500.0,
        )
        t2 = _make_trade(
            entry_time=datetime(2024, 6, 2, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 2, 14, 0, tzinfo=timezone.utc),
            direction="SELL", entry_price=1.11, exit_price=1.10,
            position_size=100000.0, pnl=900.0,
        )
        t3 = _make_trade(
            entry_time=datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 3, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.10, exit_price=1.09,
            position_size=100000.0, pnl=-400.0,
            exit_reason="stop_loss",
        )
        result = compute_metrics([t1, t2, t3], 10000.0)
        assert result.sharpe_ratio is not None
        # Sharpe can be any real number — just verify it's computed
        assert isinstance(result.sharpe_ratio, float)

    def test_sharpe_insufficient_trades(self):
        """Sharpe requires at least 2 trades."""
        t1 = _make_trade(
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 1, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.10, exit_price=1.11,
            position_size=100000.0, pnl=500.0,
        )
        result = compute_metrics([t1], 10000.0)
        assert result.sharpe_ratio is None

    def test_avg_hold_time(self):
        t1 = _make_trade(
            entry_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 1, 14, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.10, exit_price=1.11,
            position_size=100000.0, pnl=500.0,
        )
        t2 = _make_trade(
            entry_time=datetime(2024, 6, 2, 10, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 2, 18, 0, tzinfo=timezone.utc),
            direction="BUY", entry_price=1.10, exit_price=1.11,
            position_size=100000.0, pnl=500.0,
        )
        result = compute_metrics([t1, t2], 10000.0)
        # Hold times: 4h (14400s) and 8h (28800s), avg = 21600s
        assert result.avg_hold_time_seconds == pytest.approx(21600.0, rel=0.01)
