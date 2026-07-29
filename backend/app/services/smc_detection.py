"""SMC Detection Service — detects institutional SMC/ICT patterns from OHLCV candles.

Each detection method is a standalone function. All methods receive a list of
Candle objects (sorted chronologically) and return lists of SMCStructure objects.

Confidence scores (0.0–1.0) are based on candle size relative to ATR, volume,
and multiple confirmations.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Sequence

from app.models.candle import Candle
from app.models.smc_structure import SMCStructure

logger = logging.getLogger(__name__)

# Default tolerance for "equal" price levels (0.05% of price)
EQUAL_LEVEL_TOLERANCE = 0.0005


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    """Compute simple ATR. Returns 0 if insufficient data."""
    n = len(closes)
    if n < period + 1:
        return 0.0

    tr_values: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_values.append(tr)

    if not tr_values:
        return 0.0
    return sum(tr_values[-period:]) / period


def _find_swing_highs(highs: list[float], lookback: int = 5) -> list[tuple[int, float]]:
    """Find swing high indices and values. Returns list of (index, value).

    A swing high is a point that is greater than all points within 'lookback'
    candles to the left AND to the right. For points near the end of the array,
    we only require lookback candles to the left.
    """
    results: list[tuple[int, float]] = []
    if len(highs) < lookback + 1:
        return results
    for i in range(lookback, len(highs)):
        window_left = highs[i - lookback : i]
        center_val = highs[i]
        left_max = max(window_left)
        if center_val <= left_max:
            continue
        # Check right side — but be lenient near the end
        right_len = min(lookback, len(highs) - i - 1)
        if right_len > 0:
            window_right = highs[i + 1 : i + 1 + right_len]
            right_max = max(window_right)
            if center_val <= right_max:
                continue
        results.append((i, center_val))
    return results


def _find_swing_lows(lows: list[float], lookback: int = 5) -> list[tuple[int, float]]:
    """Find swing low indices and values. Returns list of (index, value).

    A swing low is a point that is less than all points within 'lookback'
    candles to the left AND to the right. For points near the end of the array,
    we only require lookback candles to the left.
    """
    results: list[tuple[int, float]] = []
    if len(lows) < lookback + 1:
        return results
    for i in range(lookback, len(lows)):
        window_left = lows[i - lookback : i]
        center_val = lows[i]
        left_min = min(window_left)
        if center_val >= left_min:
            continue
        right_len = min(lookback, len(lows) - i - 1)
        if right_len > 0:
            window_right = lows[i + 1 : i + 1 + right_len]
            right_min = min(window_right)
            if center_val >= right_min:
                continue
        results.append((i, center_val))
    return results


def _confidence_from_body_ratio(candle: Candle, atr_value: float) -> float:
    """Compute confidence based on candle body relative to ATR."""
    if atr_value <= 0:
        return 0.3
    body = abs(candle.close - candle.open)
    ratio = min(body / atr_value, 2.0)
    return min(ratio * 0.5 + 0.3, 1.0)


def _volume_confidence(volume: int, avg_volume: float) -> float:
    """Confidence boost from above-average volume."""
    if avg_volume <= 0:
        return 0.5
    ratio = min(volume / avg_volume, 3.0)
    return min(ratio * 0.3 + 0.4, 1.0)


# ── Public Detection Methods ─────────────────────────────────────────────────────


def detect_bos(
    candles: Sequence[Candle],
    symbol: str,
    timeframe: str,
    lookback: int = 5,
) -> list[SMCStructure]:
    """Detect Break of Structure (BOS).

    Bullish BOS: price closes above a prior swing high.
    Bearish BOS: price closes below a prior swing low.
    """
    if len(candles) < lookback * 2 + 3:
        return []

    results: list[SMCStructure] = []
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_val = _atr(highs, lows, closes, 14) or 0.0001
    avg_vol = sum(c.tick_volume for c in candles) / max(len(candles), 1)

    sh = _find_swing_highs(highs, lookback)
    sl = _find_swing_lows(lows, lookback)

    latest = candles[-1]
    current_close = latest.close

    # Bullish BOS: check if close breaks a prior swing high
    for idx, sh_val in sh:
        if idx >= len(candles) - 2:
            continue  # Skip very recent swings; need at least one candle after
        if current_close > sh_val:
            body_conf = _confidence_from_body_ratio(latest, atr_val)
            vol_conf = _volume_confidence(latest.tick_volume, avg_vol)
            confidence = round((body_conf + vol_conf) / 2.0, 4)
            results.append(SMCStructure(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=latest.timestamp,
                structure_type="bos",
                direction="bullish",
                key_level=round(sh_val, 5),
                price_mid=round(current_close, 5),
                confidence=confidence,
            ))

    # Bearish BOS: check if close breaks a prior swing low
    for idx, sl_val in sl:
        if idx >= len(candles) - 2:
            continue
        if current_close < sl_val:
            body_conf = _confidence_from_body_ratio(latest, atr_val)
            vol_conf = _volume_confidence(latest.tick_volume, avg_vol)
            confidence = round((body_conf + vol_conf) / 2.0, 4)
            results.append(SMCStructure(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=latest.timestamp,
                structure_type="bos",
                direction="bearish",
                key_level=round(sl_val, 5),
                price_mid=round(current_close, 5),
                confidence=confidence,
            ))

    return results


def detect_choch(
    candles: Sequence[Candle],
    symbol: str,
    timeframe: str,
    lookback: int = 5,
) -> list[SMCStructure]:
    """Detect Change of Character (CHoCH).

    A CHoCH occurs when the market trend reverses. We detect this by:
    1. Determining the trend in the first half of candles (using SMA slope)
    2. Detecting BOS in the second half in the opposite direction

    Bullish CHoCH: prior trend was bearish, now a bullish BOS appears.
    Bearish CHoCH: prior trend was bullish, now a bearish BOS appears.
    """
    if len(candles) < lookback * 4 + 5:
        return []

    results: list[SMCStructure] = []
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_val = _atr(highs, lows, closes, 14) or 0.0001
    avg_vol = sum(c.tick_volume for c in candles) / max(len(candles), 1)

    mid = len(candles) // 2
    earlier = list(candles[:mid])
    later = list(candles[mid:])

    # Determine earlier trend by comparing first quarter to second quarter prices
    q1 = earlier[:len(earlier)//2]
    q2 = earlier[len(earlier)//2:]
    if not q1 or not q2:
        return results

    q1_avg = sum(c.close for c in q1) / len(q1)
    q2_avg = sum(c.close for c in q2) / len(q2)
    earlier_trend = "bullish" if q2_avg > q1_avg else "bearish"

    # Detect BOS in the later half
    later_bos = detect_bos(later, symbol, timeframe, lookback=lookback)

    if not later_bos:
        return results

    later_bullish = any(b.direction == "bullish" for b in later_bos)
    later_bearish = any(b.direction == "bearish" for b in later_bos)

    latest = candles[-1]

    # CHoCH: earlier trend reversed by later BOS
    if earlier_trend == "bullish" and later_bearish:
        body_conf = _confidence_from_body_ratio(latest, atr_val)
        vol_conf = _volume_confidence(latest.tick_volume, avg_vol)
        confidence = round(min((body_conf + vol_conf) / 2.0 + 0.1, 1.0), 4)
        results.append(SMCStructure(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=latest.timestamp,
            structure_type="choch",
            direction="bearish",
            key_level=round(latest.close, 5),
            price_mid=round(latest.close, 5),
            confidence=confidence,
        ))

    if earlier_trend == "bearish" and later_bullish:
        body_conf = _confidence_from_body_ratio(latest, atr_val)
        vol_conf = _volume_confidence(latest.tick_volume, avg_vol)
        confidence = round(min((body_conf + vol_conf) / 2.0 + 0.1, 1.0), 4)
        results.append(SMCStructure(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=latest.timestamp,
            structure_type="choch",
            direction="bullish",
            key_level=round(latest.close, 5),
            price_mid=round(latest.close, 5),
            confidence=confidence,
        ))

    return results


def detect_order_blocks(
    candles: Sequence[Candle],
    symbol: str,
    timeframe: str,
    atr_multiplier: float = 2.0,
    lookback: int = 10,
) -> list[SMCStructure]:
    """Detect Order Blocks.

    Bullish OB: the last bearish candle before a strong bullish rally (2x ATR move).
    Bearish OB: the last bullish candle before a strong bearish drop (2x ATR move).
    """
    n = len(candles)
    if n < lookback + 3:
        return []

    results: list[SMCStructure] = []
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_val = _atr(highs, lows, closes, 14) or 0.0001
    avg_vol = sum(c.tick_volume for c in candles) / max(n, 1)
    threshold = atr_multiplier * atr_val

    # Scan backwards to find impulsive moves
    for i in range(lookback, n - 1):
        # Check for bullish impulsive move from candle i to i+1
        move = closes[i + 1] - closes[i]
        if move > threshold:
            # Find the last bearish candle before this move
            for j in range(i, max(i - lookback, -1), -1):
                c = candles[j]
                if c.close < c.open:  # bearish candle
                    results.append(SMCStructure(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c.timestamp,
                        structure_type="order_block",
                        direction="bullish",
                        price_high=round(c.high, 5),
                        price_low=round(c.low, 5),
                        price_mid=round((c.high + c.low) / 2.0, 5),
                        confidence=round(_confidence_from_body_ratio(c, atr_val), 4),
                    ))
                    break

        # Check for bearish impulsive move
        if -move > threshold:
            for j in range(i, max(i - lookback, -1), -1):
                c = candles[j]
                if c.close > c.open:  # bullish candle
                    results.append(SMCStructure(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=c.timestamp,
                        structure_type="order_block",
                        direction="bearish",
                        price_high=round(c.high, 5),
                        price_low=round(c.low, 5),
                        price_mid=round((c.high + c.low) / 2.0, 5),
                        confidence=round(_confidence_from_body_ratio(c, atr_val), 4),
                    ))
                    break

    return results


def detect_fvg(
    candles: Sequence[Candle],
    symbol: str,
    timeframe: str,
) -> list[SMCStructure]:
    """Detect Fair Value Gaps (FVG).

    Bullish FVG: candle[i].low > candle[i-2].high (gap to upside)
    Bearish FVG: candle[i].high < candle[i-2].low (gap to downside)

    Requires 3 candles. The gap exists between candle[i-2] and candle[i].
    """
    n = len(candles)
    if n < 3:
        return []

    results: list[SMCStructure] = []
    atr_val = _atr(
        [c.high for c in candles],
        [c.low for c in candles],
        [c.close for c in candles],
        14,
    ) or 0.0001

    for i in range(2, n):
        c0 = candles[i - 2]  # oldest
        c2 = candles[i]      # newest

        # Bullish FVG: gap up (low of newest > high of two candles back)
        if c2.low > c0.high:
            gap_size = c2.low - c0.high
            # Confidence based on gap size relative to ATR
            confidence = round(min(gap_size / atr_val * 0.5 + 0.3, 1.0), 4)
            results.append(SMCStructure(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=c2.timestamp,
                structure_type="fvg",
                direction="bullish",
                price_low=round(c0.high, 5),   # gap bottom
                price_high=round(c2.low, 5),    # gap top
                price_mid=round((c0.high + c2.low) / 2.0, 5),
                confidence=confidence,
            ))

        # Bearish FVG: gap down (high of newest < low of two candles back)
        if c2.high < c0.low:
            gap_size = c0.low - c2.high
            confidence = round(min(gap_size / atr_val * 0.5 + 0.3, 1.0), 4)
            results.append(SMCStructure(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=c2.timestamp,
                structure_type="fvg",
                direction="bearish",
                price_high=round(c0.low, 5),   # gap top
                price_low=round(c2.high, 5),    # gap bottom
                price_mid=round((c0.low + c2.high) / 2.0, 5),
                confidence=confidence,
            ))

    return results


def detect_liquidity_sweeps(
    candles: Sequence[Candle],
    symbol: str,
    timeframe: str,
    lookback: int = 5,
    reversal_threshold: float = 0.3,
) -> list[SMCStructure]:
    """Detect Liquidity Sweeps (stop hunts).

    Buy-side sweep: price briefly breaks above a swing high, then immediately reverses
    (closes back below the swing high within a few candles).

    Sell-side sweep: price briefly breaks below a swing low, then immediately reverses
    (closes back above the swing low within a few candles).
    """
    n = len(candles)
    if n < lookback * 2 + 5:
        return []

    results: list[SMCStructure] = []
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_val = _atr(highs, lows, closes, 14) or 0.0001

    sh = _find_swing_highs(highs, lookback)
    sl = _find_swing_lows(lows, lookback)

    # For each swing high, check if it was breached then reversed
    for sh_idx, sh_val in sh:
        if sh_idx >= n - 5:
            continue  # Need room for reversal after the sweep
        # Look at candles after the swing high — extend window to 8 candles
        swept = False
        swept_idx = sh_idx
        for j in range(sh_idx + 1, min(n - 1, sh_idx + 8)):
            if candles[j].high > sh_val:
                swept = True
                swept_idx = j
                break
        if not swept:
            continue
        # Check for reversal: close must fall back below swing high within 4 candles
        for j in range(swept_idx + 1, min(n, swept_idx + 5)):
            if candles[j].close < sh_val:
                reversal_size = abs(sh_val - candles[j].close)
                # Only count significant reversals
                if reversal_size > reversal_threshold * atr_val:
                    results.append(SMCStructure(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=candles[swept_idx].timestamp,
                        structure_type="liquidity_sweep",
                        direction="bullish",  # buyside sweep: hit highs then dropped
                        key_level=round(sh_val, 5),
                        price_low=round(candles[j].close, 5),
                        confidence=round(min(reversal_size / atr_val * 0.4 + 0.4, 1.0), 4),
                    ))
                break

    # For each swing low, check if it was breached then reversed
    for sl_idx, sl_val in sl:
        if sl_idx >= n - 5:
            continue
        swept = False
        swept_idx = sl_idx
        for j in range(sl_idx + 1, min(n - 1, sl_idx + 8)):
            if candles[j].low < sl_val:
                swept = True
                swept_idx = j
                break
        if not swept:
            continue
        for j in range(swept_idx + 1, min(n, swept_idx + 5)):
            if candles[j].close > sl_val:
                reversal_size = abs(candles[j].close - sl_val)
                if reversal_size > reversal_threshold * atr_val:
                    results.append(SMCStructure(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=candles[swept_idx].timestamp,
                        structure_type="liquidity_sweep",
                        direction="bearish",  # sellside sweep: hit lows then pumped
                        key_level=round(sl_val, 5),
                        price_high=round(candles[j].close, 5),
                        confidence=round(min(reversal_size / atr_val * 0.4 + 0.4, 1.0), 4),
                    ))
                break

    return results


def detect_equal_highs_lows(
    candles: Sequence[Candle],
    symbol: str,
    timeframe: str,
    lookback: int = 20,
    tolerance: float = EQUAL_LEVEL_TOLERANCE,
) -> list[SMCStructure]:
    """Detect Equal Highs / Equal Lows (liquidity pools).

    Equal Highs: two or more swing highs within tolerance of each other.
    Equal Lows: two or more swing lows within tolerance of each other.
    """
    n = len(candles)
    if n < lookback:
        return []

    results: list[SMCStructure] = []
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_val = _atr(highs, lows, closes, 14) or 0.0001

    # Use a wider lookback for swing detection on the recent window
    swing_lb = 3
    sh = _find_swing_highs(highs, swing_lb)
    sl = _find_swing_lows(lows, swing_lb)

    # Filter to recent swings (within lookback)
    recent_sh = [(i, v) for i, v in sh if i >= n - lookback]
    recent_sl = [(i, v) for i, v in sl if i >= n - lookback]

    # Cluster equal highs
    seen_high_clusters: set[str] = set()
    for i in range(len(recent_sh)):
        for j in range(i + 1, len(recent_sh)):
            val1 = recent_sh[i][1]
            val2 = recent_sh[j][1]
            if val2 == 0:
                continue
            pct_diff = abs(val1 - val2) / val2
            if pct_diff <= tolerance:
                cluster_key = f"{round(val1, 5)}_{round(val2, 5)}"
                if cluster_key in seen_high_clusters:
                    continue
                seen_high_clusters.add(cluster_key)
                avg_level = round((val1 + val2) / 2.0, 5)
                occurrences = [
                    candles[recent_sh[i][0]].timestamp.isoformat(),
                    candles[recent_sh[j][0]].timestamp.isoformat(),
                ]
                results.append(SMCStructure(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candles[max(recent_sh[i][0], recent_sh[j][0])].timestamp,
                    structure_type="equal_highs",
                    direction="bearish",  # Equal highs = resistance/liquidity above
                    price_high=avg_level,
                    price_mid=avg_level,
                    confidence=round(min(0.5 + (2.0 * atr_val / avg_level * 100) * 0.1, 0.9), 4),
                    details=json.dumps({"occurrences": occurrences, "level": avg_level}),
                ))

    # Cluster equal lows
    seen_low_clusters: set[str] = set()
    for i in range(len(recent_sl)):
        for j in range(i + 1, len(recent_sl)):
            val1 = recent_sl[i][1]
            val2 = recent_sl[j][1]
            if val2 == 0:
                continue
            pct_diff = abs(val1 - val2) / val2
            if pct_diff <= tolerance:
                cluster_key = f"{round(val1, 5)}_{round(val2, 5)}"
                if cluster_key in seen_low_clusters:
                    continue
                seen_low_clusters.add(cluster_key)
                avg_level = round((val1 + val2) / 2.0, 5)
                occurrences = [
                    candles[recent_sl[i][0]].timestamp.isoformat(),
                    candles[recent_sl[j][0]].timestamp.isoformat(),
                ]
                results.append(SMCStructure(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candles[max(recent_sl[i][0], recent_sl[j][0])].timestamp,
                    structure_type="equal_lows",
                    direction="bullish",  # Equal lows = support/liquidity below
                    price_low=avg_level,
                    price_mid=avg_level,
                    confidence=round(min(0.5 + (2.0 * atr_val / avg_level * 100) * 0.1, 0.9), 4),
                    details=json.dumps({"occurrences": occurrences, "level": avg_level}),
                ))

    return results


def detect_premium_discount(
    candles: Sequence[Candle],
    symbol: str,
    timeframe: str,
    lookback: int = 50,
) -> list[SMCStructure]:
    """Detect Premium / Discount zones.

    Uses the most recent significant swing high and swing low from the lookback window.
    Premium: price in upper 50% of range (0.5 to 1.0).
    Discount: price in lower 50% of range (0.0 to 0.5).
    Equilibrium: price within 1% of 0.5.

    Returns a single-element list (latest assessment).
    """
    n = len(candles)
    if n < lookback:
        return []

    window = list(candles)[-lookback:]
    highs = [c.high for c in window]
    lows = [c.low for c in window]

    swing_high = max(highs)
    swing_low = min(lows)

    if swing_high <= swing_low:
        return []

    latest = candles[-1]
    current_price = latest.close

    position_pct = (current_price - swing_low) / (swing_high - swing_low)
    position_pct = max(0.0, min(1.0, position_pct))

    if abs(position_pct - 0.5) < 0.01:
        zone = "equilibrium"
    elif position_pct > 0.5:
        zone = "premium"
    else:
        zone = "discount"

    # Confidence higher when price is clearly in premium/discount extremes
    distance_from_mid = abs(position_pct - 0.5)
    confidence = round(0.4 + distance_from_mid * 0.6, 4)

    return [SMCStructure(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=latest.timestamp,
        structure_type="premium_discount",
        direction="bullish" if zone == "discount" else "bearish",
        price_high=round(swing_high, 5),
        price_low=round(swing_low, 5),
        price_mid=round(current_price, 5),
        confidence=confidence,
        details=json.dumps({
            "zone_type": zone,
            "position_pct": round(position_pct, 4),
            "swing_high": round(swing_high, 5),
            "swing_low": round(swing_low, 5),
        }),
    )]


class SMCDetectionService:
    """Orchestrates all SMC detection methods.

    Usage:
        service = SMCDetectionService()
        structures = service.detect_all(candles, "EURUSD", "H1")
    """

    def detect_all(
        self,
        candles: Sequence[Candle],
        symbol: str,
        timeframe: str,
    ) -> list[SMCStructure]:
        """Run all detection methods and return combined results."""
        if not candles:
            return []

        all_structures: list[SMCStructure] = []

        all_structures.extend(detect_bos(candles, symbol, timeframe))
        all_structures.extend(detect_choch(candles, symbol, timeframe))
        all_structures.extend(detect_order_blocks(candles, symbol, timeframe))
        all_structures.extend(detect_fvg(candles, symbol, timeframe))
        all_structures.extend(detect_liquidity_sweeps(candles, symbol, timeframe))
        all_structures.extend(detect_equal_highs_lows(candles, symbol, timeframe))
        all_structures.extend(detect_premium_discount(candles, symbol, timeframe))

        return all_structures
