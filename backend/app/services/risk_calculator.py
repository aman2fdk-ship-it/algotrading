"""RiskCalculator — pure functions for position sizing, margin, and risk metrics.

All calculations are advisory only. No external API calls — all math is self-contained.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD",
    "USDCAD", "USDCHF", "XAUUSD", "BTCUSD", "ETHUSD",
]

STANDARD_LOT_UNITS = 100_000
MINI_LOT_UNITS = 10_000
MICRO_LOT_UNITS = 1_000

MARGIN_CALL_LEVEL = 100.0   # margin call at 100%
STOP_OUT_LEVEL = 50.0       # stop out at 50%


# ── Pip value and pip size tables ──────────────────────────────────────────────
# Pip sizes per symbol (the price increment considered one pip)
PIP_SIZES: dict[str, float] = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
    "AUDUSD": 0.0001,
    "NZDUSD": 0.0001,
    "USDCAD": 0.0001,
    "USDCHF": 0.0001,
    "XAUUSD": 0.10,
    "BTCUSD": 1.0,
    "ETHUSD": 0.10,
}

# Pip value in account currency (USD) per 1 standard lot
PIP_VALUES: dict[str, float] = {
    "EURUSD": 10.0,
    "GBPUSD": 10.0,
    "USDJPY": 9.15,
    "AUDUSD": 10.0,
    "NZDUSD": 10.0,
    "USDCAD": 7.50,
    "USDCHF": 11.0,
    "XAUUSD": 10.0,
    "BTCUSD": 1.0,
    "ETHUSD": 0.10,
}

# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class PositionSizeResult:
    """Result of a position size calculation."""
    position_size: float      # total position value in account currency
    risk_amount: float        # amount at risk (balance * risk_pct / 100)
    stop_loss_pips: float     # distance from entry to SL in pips
    lot_size: float           # position size in standard lots (100,000 units)
    mini_lots: float          # position size in mini lots (10,000 units)
    micro_lots: float         # position size in micro lots (1,000 units)


@dataclass
class MarginResult:
    """Result of a margin calculation."""
    required_margin: float    # position_size / leverage
    margin_level: float       # (equity / used_margin) * 100
    margin_call_level: float  # 100%
    stop_out_level: float     # 50%


@dataclass
class RiskCalculationResult:
    """Complete risk calculation combining position sizing and margin."""
    symbol: str
    account_balance: float
    risk_percentage: float
    entry_price: float
    stop_loss: float
    leverage: float
    # Position sizing
    position_size: float
    risk_amount: float
    stop_loss_pips: float
    lot_size: float
    mini_lots: float
    micro_lots: float
    # Margin
    required_margin: float
    # Take profit targets
    take_profit_1: float | None  # 1.5R target
    take_profit_2: float | None  # 2R target
    potential_profit_tp1: float | None
    potential_profit_tp2: float | None
    risk_reward_ratio_tp1: float | None
    risk_reward_ratio_tp2: float | None
    # Pip info
    pip_size: float
    pip_value: float


# ── Pure calculation functions ─────────────────────────────────────────────────


def get_pip_size(symbol: str) -> float:
    """Return the pip size (price increment) for a symbol.

    Raises:
        ValueError: if the symbol is not supported.
    """
    symbol = symbol.upper()
    if symbol not in PIP_SIZES:
        raise ValueError(
            f"Unsupported symbol '{symbol}'. Supported: {sorted(PIP_SIZES.keys())}"
        )
    return PIP_SIZES[symbol]


def get_pip_value(symbol: str) -> float:
    """Return the pip value in USD per 1 standard lot for a symbol.

    Raises:
        ValueError: if the symbol is not supported.
    """
    symbol = symbol.upper()
    if symbol not in PIP_VALUES:
        raise ValueError(
            f"Unsupported symbol '{symbol}'. Supported: {sorted(PIP_VALUES.keys())}"
        )
    return PIP_VALUES[symbol]


def get_all_pip_values() -> dict[str, dict[str, float]]:
    """Return all symbol pip sizes and values."""
    return {
        sym: {
            "pip_size": PIP_SIZES[sym],
            "pip_value_per_lot": PIP_VALUES[sym],
        }
        for sym in SUPPORTED_SYMBOLS
    }


def calculate_position_size(
    account_balance: float,
    risk_percentage: float,
    entry_price: float,
    stop_loss: float,
    symbol: str,
) -> PositionSizeResult:
    """Calculate position size based on risk parameters.

    Args:
        account_balance: Total account equity in account currency.
        risk_percentage: % of account to risk per trade (e.g., 1.0 = 1%).
        entry_price: Planned entry price.
        stop_loss: Stop loss price.
        symbol: Trading symbol code (e.g., "EURUSD").

    Returns:
        PositionSizeResult with position_size, risk_amount, stop_loss_pips,
        lot_size, mini_lots, micro_lots.

    Raises:
        ValueError: if inputs are invalid (negative balance, zero SL distance, etc.)
    """
    symbol = symbol.upper()
    pip_size = get_pip_size(symbol)
    pip_value = get_pip_value(symbol)

    if account_balance <= 0:
        raise ValueError("Account balance must be positive.")
    if risk_percentage < 0:
        raise ValueError("Risk percentage must be non-negative.")
    if entry_price <= 0:
        raise ValueError("Entry price must be positive.")
    if stop_loss <= 0:
        raise ValueError("Stop loss must be positive.")

    # Calculate risk amount
    risk_amount = account_balance * (risk_percentage / 100.0)

    # Calculate stop loss distance in pips
    sl_distance = abs(entry_price - stop_loss)
    stop_loss_pips = sl_distance / pip_size

    if stop_loss_pips <= 0:
        raise ValueError(
            f"Stop loss distance is zero. Entry={entry_price}, SL={stop_loss}"
        )

    # Position size formula: risk_amount / (stop_loss_pips * pip_value)
    # Result is in standard lots. pip_value is per 1 standard lot.
    lot_count = risk_amount / (stop_loss_pips * pip_value)

    # Convert to units (position_size is total position value in account currency units)
    position_size = lot_count * STANDARD_LOT_UNITS
    mini_lots = position_size / MINI_LOT_UNITS
    micro_lots = position_size / MICRO_LOT_UNITS

    return PositionSizeResult(
        position_size=round(position_size, 2),
        risk_amount=round(risk_amount, 2),
        stop_loss_pips=round(stop_loss_pips, 2),
        lot_size=round(lot_count, 4),
        mini_lots=round(mini_lots, 2),
        micro_lots=round(micro_lots, 2),
    )


def calculate_margin(
    position_size: float,
    leverage: float,
    equity: float | None = None,
) -> MarginResult:
    """Calculate required margin and margin level.

    Args:
        position_size: Total position value in account currency.
        leverage: Leverage ratio (e.g., 100 = 100:1).
        equity: Current account equity (for margin level calculation).
                If None, margin_level is computed against required_margin.

    Returns:
        MarginResult with required_margin, margin_level, call/stop-out levels.

    Raises:
        ValueError: if leverage <= 0 or position_size < 0.
    """
    if position_size < 0:
        raise ValueError("Position size must be non-negative.")
    if leverage <= 0:
        raise ValueError("Leverage must be positive.")

    required_margin = position_size / leverage

    if equity is None:
        equity = required_margin * 2.0  # default: healthy margin

    margin_level = (equity / required_margin) * 100.0 if required_margin > 0 else float("inf")

    return MarginResult(
        required_margin=round(required_margin, 2),
        margin_level=round(margin_level, 2),
        margin_call_level=MARGIN_CALL_LEVEL,
        stop_out_level=STOP_OUT_LEVEL,
    )


def calculate_profit_targets(
    entry_price: float,
    stop_loss: float,
) -> tuple[float | None, float | None]:
    """Calculate TP1 (1.5R) and TP2 (2R) levels.

    For long trades: tp = entry + (entry - sl) * multiplier
    For short trades: tp = entry - (sl - entry) * multiplier
    Direction is inferred from stop_loss relative to entry.

    Returns:
        Tuple of (tp1, tp2). If entry == SL, returns (None, None).
    """
    if entry_price == stop_loss:
        return (None, None)

    risk_distance = abs(entry_price - stop_loss)

    if stop_loss < entry_price:
        # Long trade: SL below entry
        tp1 = entry_price + risk_distance * 1.5
        tp2 = entry_price + risk_distance * 2.0
    else:
        # Short trade: SL above entry
        tp1 = entry_price - risk_distance * 1.5
        tp2 = entry_price - risk_distance * 2.0

    return (round(tp1, 5), round(tp2, 5))


def calculate_risk_metrics(
    account_balance: float,
    risk_percentage: float,
    entry_price: float,
    stop_loss: float,
    symbol: str,
    leverage: float,
) -> RiskCalculationResult:
    """Combined risk calculation: position sizing + margin + profit targets.

    Args:
        account_balance: Total account equity.
        risk_percentage: % of account to risk (e.g., 1.0 = 1%).
        entry_price: Planned entry price.
        stop_loss: Stop loss price.
        symbol: Trading symbol code (e.g., "EURUSD").
        leverage: Leverage ratio (e.g., 100).

    Returns:
        RiskCalculationResult with full risk breakdown.

    Raises:
        ValueError: if any inputs are invalid.
    """
    symbol = symbol.upper()
    if symbol not in PIP_SIZES:
        raise ValueError(
            f"Unsupported symbol '{symbol}'. Supported: {sorted(PIP_SIZES.keys())}"
        )

    pos_result = calculate_position_size(
        account_balance, risk_percentage, entry_price, stop_loss, symbol
    )
    margin_result = calculate_margin(
        pos_result.position_size, leverage, account_balance
    )

    tp1, tp2 = calculate_profit_targets(entry_price, stop_loss)

    pip_size = PIP_SIZES[symbol]
    pip_value = PIP_VALUES[symbol]

    # Profit at TP levels
    if tp1 is not None and tp2 is not None:
        risk_distance = abs(entry_price - stop_loss)
        tp1_distance = abs(tp1 - entry_price) / pip_size
        tp2_distance = abs(tp2 - entry_price) / pip_size
        potential_profit_tp1 = round(tp1_distance * pip_value * pos_result.lot_size, 2)
        potential_profit_tp2 = round(tp2_distance * pip_value * pos_result.lot_size, 2)
        risk_reward_tp1 = round(tp1_distance / pos_result.stop_loss_pips, 2) if pos_result.stop_loss_pips > 0 else None
        risk_reward_tp2 = round(tp2_distance / pos_result.stop_loss_pips, 2) if pos_result.stop_loss_pips > 0 else None
    else:
        potential_profit_tp1 = None
        potential_profit_tp2 = None
        risk_reward_tp1 = None
        risk_reward_tp2 = None

    return RiskCalculationResult(
        symbol=symbol,
        account_balance=account_balance,
        risk_percentage=risk_percentage,
        entry_price=entry_price,
        stop_loss=stop_loss,
        leverage=leverage,
        position_size=pos_result.position_size,
        risk_amount=pos_result.risk_amount,
        stop_loss_pips=pos_result.stop_loss_pips,
        lot_size=pos_result.lot_size,
        mini_lots=pos_result.mini_lots,
        micro_lots=pos_result.micro_lots,
        required_margin=margin_result.required_margin,
        take_profit_1=tp1,
        take_profit_2=tp2,
        potential_profit_tp1=potential_profit_tp1,
        potential_profit_tp2=potential_profit_tp2,
        risk_reward_ratio_tp1=risk_reward_tp1,
        risk_reward_ratio_tp2=risk_reward_tp2,
        pip_size=pip_size,
        pip_value=pip_value,
    )
