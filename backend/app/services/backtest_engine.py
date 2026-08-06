"""BacktestEngine — walks forward through historical candles, simulates trades using AI decisions.

Pure simulation, advisory only. No real money.
"""

from __future__ import annotations

import json
import logging
import uuid as uuid_mod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.backtest import BacktestRun, BacktestTrade
from app.models.candle import Candle
from app.repositories.candle_repository import CandleRepository
from app.repositories.indicator_repository import IndicatorRepository
from app.repositories.smc_repository import SMCRepository
from app.repositories.backtest_repository import BacktestRepository
from app.services.ai_decision import AIDecisionService, DecisionResult
from app.services.risk_calculator import calculate_risk_metrics
from app.services.backtest_metrics import (
    TradeRecord,
    compute_metrics,
    MetricsResult,
)

logger = logging.getLogger(__name__)

# Supported timeframes
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

# Minimum candles needed before any decision (warm-up)
MIN_WARMUP_CANDLES = 50


@dataclass
class _OpenPosition:
    """Internal state for an open position during simulation."""

    direction: str  # BUY or SELL
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float  # TP1 — close at first TP hit
    position_size: float


@dataclass
class BacktestResult:
    """Complete backtest output."""

    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    risk_percentage: float
    final_balance: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float | None
    max_drawdown: float
    max_drawdown_amount: float
    expectancy: float
    sharpe_ratio: float | None
    avg_win: float | None
    avg_loss: float | None
    largest_win: float | None
    largest_loss: float | None
    avg_hold_time: float | None  # seconds
    equity_curve: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    monthly_performance: list[dict] = field(default_factory=list)
    run_id: str | None = None


class BacktestEngine:
    """Walk-forward backtesting engine.

    Simulates trading by iterating through historical candles,
    calling the AI decision engine at each step, and tracking
    simulated trade outcomes with SL/TP logic.

    Public API:
        run(symbol, timeframe, start_date, end_date, initial_balance,
            risk_percentage, user_id) -> BacktestResult
    """

    def __init__(
        self,
        candle_repo: CandleRepository,
        indicator_repo: IndicatorRepository,
        smc_repo: SMCRepository,
        backtest_repo: BacktestRepository | None = None,
    ) -> None:
        self._candle_repo = candle_repo
        self._indicator_repo = indicator_repo
        self._smc_repo = smc_repo
        self._backtest_repo = backtest_repo

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float,
        risk_percentage: float,
        user_id: str,
    ) -> BacktestResult:
        """Run a full backtest simulation.

        Args:
            symbol: Trading symbol (e.g. "EURUSD").
            timeframe: Timeframe (e.g. "H1").
            start_date: Start of historical data range.
            end_date: End of historical data range.
            initial_balance: Starting account balance.
            risk_percentage: % risk per trade (e.g. 1.0 = 1%).
            user_id: UUID of the user running the backtest.
        """
        symbol = symbol.upper()
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Invalid timeframe '{timeframe}'. Supported: {TIMEFRAMES}")

        # Load candles
        candles = await self._candle_repo.get_range(symbol, timeframe, start_date, end_date)
        candles = list(candles)

        if len(candles) < MIN_WARMUP_CANDLES:
            logger.warning(
                "Only %d candles loaded for %s/%s — minimum %d needed for warm-up.",
                len(candles), symbol, timeframe, MIN_WARMUP_CANDLES,
            )

        logger.info(
            "Starting backtest: %s/%s from %s to %s (%d candles)",
            symbol, timeframe, start_date, end_date, len(candles),
        )

        # Build AI service
        ai_service = AIDecisionService(
            indicator_repo=self._indicator_repo,
            smc_repo=self._smc_repo,
            candle_repo=self._candle_repo,
        )

        # Simulation state
        balance = initial_balance
        open_position: _OpenPosition | None = None
        trades: list[TradeRecord] = []

        # Walk forward
        for i, candle in enumerate(candles):
            # ── Check open position ──────────────────────────────────────────
            if open_position is not None:
                exit_result = self._check_exit(candle, open_position)

                if exit_result is not None:
                    exit_price, exit_reason = exit_result
                    pnl = self._calc_pnl(
                        open_position.direction,
                        open_position.entry_price,
                        exit_price,
                        open_position.position_size,
                    )
                    pnl_pct = (pnl / balance * 100.0) if balance > 0 else 0.0

                    trades.append(TradeRecord(
                        entry_time=open_position.entry_time,
                        exit_time=candle.timestamp,
                        direction=open_position.direction,
                        entry_price=open_position.entry_price,
                        exit_price=exit_price,
                        position_size=open_position.position_size,
                        pnl=round(pnl, 2),
                        exit_reason=exit_reason,
                    ))

                    balance += pnl
                    open_position = None
                    continue  # skip AI decision for this candle after exit

            # ── Skip AI decisions during warm-up ─────────────────────────────
            if i < MIN_WARMUP_CANDLES:
                continue

            # ── Get AI decision ──────────────────────────────────────────────
            # Update the candle_repo session has the range; AI service reads from DB
            # In backtest context, we rely on the repo session being pre-loaded
            # with indicator data. The AI analyzes current DB state.
            try:
                decision = await ai_service.analyze(symbol)
            except Exception as e:
                logger.warning("AI analysis failed at candle %s: %s", candle.timestamp, e)
                continue

            # ── Open new position if signal ──────────────────────────────────
            if open_position is None and decision.decision in ("BUY", "SELL"):
                if decision.entry_price is None or decision.stop_loss is None:
                    continue  # incomplete decision

                entry_price = candle.close  # execute at candle close

                # Determine TP: use TP1, or TP2 if TP1 is None
                tp = decision.take_profit_1
                if tp is None:
                    tp = decision.take_profit_2
                if tp is None:
                    continue  # no TP set — can't open trade

                # Calculate position size via RiskCalculator
                try:
                    risk_result = calculate_risk_metrics(
                        account_balance=balance,
                        risk_percentage=risk_percentage,
                        entry_price=entry_price,
                        stop_loss=decision.stop_loss,
                        symbol=symbol,
                        leverage=100.0,  # default for simulation
                    )
                except ValueError as e:
                    logger.warning("Risk calculation failed: %s", e)
                    continue

                open_position = _OpenPosition(
                    direction=decision.decision,
                    entry_time=candle.timestamp,
                    entry_price=entry_price,
                    stop_loss=decision.stop_loss,
                    take_profit=tp,
                    position_size=risk_result.position_size,
                )

        # ── Close any remaining open position at end of data ────────────────
        if open_position is not None and candles:
            last_candle = candles[-1]
            exit_price = last_candle.close

            pnl = self._calc_pnl(
                open_position.direction,
                open_position.entry_price,
                exit_price,
                open_position.position_size,
            )
            pnl_pct = (pnl / balance * 100.0) if balance > 0 else 0.0

            trades.append(TradeRecord(
                entry_time=open_position.entry_time,
                exit_time=last_candle.timestamp,
                direction=open_position.direction,
                entry_price=open_position.entry_price,
                exit_price=exit_price,
                position_size=open_position.position_size,
                pnl=round(pnl, 2),
                exit_reason="end_of_data",
            ))
            balance += pnl

        # ── Compute metrics ─────────────────────────────────────────────────
        metrics = compute_metrics(trades, initial_balance)

        # Monthly performance as dicts
        monthly_dicts = [
            {
                "month": m.month,
                "return_pct": m.return_pct,
                "trades": m.trades,
                "win_rate": m.win_rate,
            }
            for m in metrics.monthly_performance
        ]

        # Trade dicts
        trade_dicts = [
            {
                "direction": t.direction,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "position_size": t.position_size,
                "pnl": t.pnl,
                "pnl_pct": round(t.pnl / initial_balance * 100, 4) if initial_balance > 0 else 0.0,
                "exit_reason": t.exit_reason,
            }
            for t in trades
        ]

        result = BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            risk_percentage=risk_percentage,
            final_balance=round(balance, 2),
            total_trades=metrics.total_trades,
            winning_trades=metrics.winning_trades,
            losing_trades=metrics.losing_trades,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            max_drawdown=metrics.max_drawdown_pct,
            max_drawdown_amount=metrics.max_drawdown_amount,
            expectancy=metrics.expectancy,
            sharpe_ratio=metrics.sharpe_ratio,
            avg_win=metrics.avg_win,
            avg_loss=metrics.avg_loss,
            largest_win=metrics.largest_win,
            largest_loss=metrics.largest_loss,
            avg_hold_time=metrics.avg_hold_time_seconds,
            equity_curve=metrics.equity_curve,
            trades=trade_dicts,
            monthly_performance=monthly_dicts,
        )

        # ── Persist to DB if repository provided ────────────────────────────
        if self._backtest_repo:
            run_id = str(uuid_mod.uuid4())
            result.run_id = run_id

            run_model = BacktestRun(
                id=run_id,
                user_id=user_id,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_balance=initial_balance,
                risk_percentage=risk_percentage,
                final_balance=result.final_balance,
                total_trades=metrics.total_trades,
                win_rate=metrics.win_rate,
                profit_factor=metrics.profit_factor,
                max_drawdown=metrics.max_drawdown_pct,
                expectancy=metrics.expectancy,
                sharpe_ratio=metrics.sharpe_ratio,
                equity_curve=json.dumps(metrics.equity_curve),
                monthly_performance=json.dumps(monthly_dicts),
            )
            self._backtest_repo.add_run(run_model)

            for t in trades:
                trade_model = BacktestTrade(
                    id=str(uuid_mod.uuid4()),
                    backtest_run_id=run_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=t.direction,
                    entry_time=t.entry_time,
                    exit_time=t.exit_time,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price,
                    position_size=t.position_size,
                    pnl=t.pnl,
                    pnl_pct=round(t.pnl / initial_balance * 100, 4) if initial_balance > 0 else 0.0,
                    exit_reason=t.exit_reason,
                )
                self._backtest_repo.add_trade(trade_model)

            await self._backtest_repo.flush()
            logger.info("Backtest %s persisted with %d trades", run_id, len(trades))

        return result

    # ── Exit logic ──────────────────────────────────────────────────────────

    @staticmethod
    def _check_exit(
        candle: Candle,
        position: _OpenPosition,
    ) -> tuple[float, str] | None:
        """Check if an open position should close on this candle.

        Returns (exit_price, exit_reason) if closed, else None.

        SL/TP detection:
        - Long: SL hit if candle.low <= stop_loss, TP if candle.high >= take_profit
        - Short: SL hit if candle.high >= stop_loss, TP if candle.low <= take_profit
        - Both hit same candle: whichever is closer to candle.open wins
        """
        direction = position.direction
        sl = position.stop_loss
        tp = position.take_profit
        open_price = candle.open

        sl_hit = False
        tp_hit = False

        if direction == "BUY":
            if candle.low <= sl:
                sl_hit = True
            if candle.high >= tp:
                tp_hit = True
        else:  # SELL
            if candle.high >= sl:
                sl_hit = True
            if candle.low <= tp:
                tp_hit = True

        if not sl_hit and not tp_hit:
            return None

        if sl_hit and not tp_hit:
            return (sl, "stop_loss")

        if tp_hit and not sl_hit:
            return (tp, "take_profit")

        # Both hit: proximity rule — whichever was closer to open hit first
        dist_sl = abs(open_price - sl)
        dist_tp = abs(open_price - tp)

        if dist_sl < dist_tp:
            return (sl, "stop_loss")
        else:
            return (tp, "take_profit")

    # ── P&L calculation ─────────────────────────────────────────────────────

    @staticmethod
    def _calc_pnl(
        direction: str,
        entry_price: float,
        exit_price: float,
        position_size: float,
    ) -> float:
        """Calculate P&L for a closed trade.

        position_size is total position value in account currency.
        For a BUY: pnl = (exit - entry) / entry * position_size
        For a SELL: pnl = (entry - exit) / entry * position_size
        """
        if entry_price <= 0:
            return 0.0

        if direction == "BUY":
            return (exit_price - entry_price) / entry_price * position_size
        else:  # SELL
            return (entry_price - exit_price) / entry_price * position_size
