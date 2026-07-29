"""Technical Analysis Service — calculates all technical indicators from OHLCV candles.

Pure Python implementation — no pandas dependency. Every method is independently
testable, accepts a list of Candle objects, and returns calculated values.
Edge cases (insufficient data, None values) are handled gracefully.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Sequence

from app.models.candle import Candle
from app.models.technical_indicator import TechnicalIndicator

logger = logging.getLogger(__name__)


def _safe_float(value: float | None) -> float:
    """Return 0.0 for None, otherwise the value."""
    return value if value is not None else 0.0


class TechnicalAnalysisService:
    """Calculates all technical indicators for a set of OHLCV candles.

    Usage:
        service = TechnicalAnalysisService()
        indicator = service.calculate_all(candles, symbol, timeframe)
    """

    # ── Public API ──────────────────────────────────────────────────────────

    def calculate_all(
        self,
        candles: Sequence[Candle],
        symbol: str,
        timeframe: str,
    ) -> TechnicalIndicator | None:
        """Calculate all indicators for the latest candle in the sequence.

        Returns None if there are no candles.
        """
        if not candles:
            return None

        latest = candles[-1]
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.tick_volume for c in candles]  # use tick_volume for VWAP

        indicator = TechnicalIndicator(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=latest.timestamp,
        )

        # ── Trend Indicators ───────────────────────────────────────────────
        indicator.ema_20 = self.calc_ema(closes, 20)
        indicator.ema_50 = self.calc_ema(closes, 50)
        indicator.ema_200 = self.calc_ema(closes, 200)

        st_dir, st_val = self.calc_supertrend(highs, lows, closes, period=10, multiplier=3.0)
        indicator.supertrend_direction = st_dir
        indicator.supertrend_value = st_val

        indicator.adx = self.calc_adx(highs, lows, closes, period=14)

        # ── Momentum Indicators ────────────────────────────────────────────
        indicator.rsi = self.calc_rsi(closes, period=14)
        indicator.macd_line, indicator.macd_signal, indicator.macd_histogram = (
            self.calc_macd(closes)
        )
        indicator.stoch_k, indicator.stoch_d = self.calc_stochastic(
            highs, lows, closes
        )

        # ── Volatility Indicators ──────────────────────────────────────────
        indicator.atr = self.calc_atr(highs, lows, closes, period=14)
        indicator.bb_upper, indicator.bb_middle, indicator.bb_lower = (
            self.calc_bollinger_bands(closes, period=20, num_std=2.0)
        )

        # ── Volume Indicators ──────────────────────────────────────────────
        indicator.vwap = self.calc_vwap(
            highs, lows, closes, volumes
        )

        # ── Price Action ───────────────────────────────────────────────────
        indicator.support_levels, indicator.resistance_levels = (
            self.calc_support_resistance(highs, lows, closes, lookback=20)
        )
        indicator.swing_high = self.calc_swing_high(highs, lookback=5)
        indicator.swing_low = self.calc_swing_low(lows, lookback=5)

        fib_levels = self.calc_fibonacci(highs, lows, lookback=50)
        if fib_levels:
            indicator.fib_236 = fib_levels.get(0.236)
            indicator.fib_382 = fib_levels.get(0.382)
            indicator.fib_500 = fib_levels.get(0.5)
            indicator.fib_618 = fib_levels.get(0.618)
            indicator.fib_786 = fib_levels.get(0.786)

        return indicator

    # ── Trend Indicators ───────────────────────────────────────────────────────

    @staticmethod
    def calc_sma(data: list[float], period: int) -> float | None:
        """Simple Moving Average."""
        if len(data) < period or period <= 0:
            return None
        return sum(data[-period:]) / period

    @staticmethod
    def calc_ema(data: list[float], period: int) -> float | None:
        """Exponential Moving Average."""
        if len(data) < period or period <= 0:
            return None
        multiplier = 2.0 / (period + 1)
        # Start EMA as SMA of first 'period' values
        ema = sum(data[:period]) / period
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    @staticmethod
    def calc_supertrend(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 10,
        multiplier: float = 3.0,
    ) -> tuple[int | None, float | None]:
        """SuperTrend indicator. Returns (direction, value).

        direction: 1 = bullish (price above Supertrend), -1 = bearish
        value: the Supertrend line value
        """
        n = len(closes)
        if n < period + 1:
            return None, None

        # Calculate ATR
        atr = TechnicalAnalysisService.calc_atr(highs, lows, closes, period)
        if atr is None:
            return None, None

        # Calculate basic upper/lower bands
        hl2 = [(h + l) / 2.0 for h, l in zip(highs, lows)]
        upper_band = [hl2[-1] + multiplier * atr]
        lower_band = [hl2[-1] - multiplier * atr]

        # Walk backwards through data to propagate bands correctly
        for i in range(n - 2, -1, -1):
            ub = hl2[i] + multiplier * atr
            lb = hl2[i] - multiplier * atr

            # Upper band: min(current ub, previous ub) if close <= previous ub
            prev_ub = upper_band[-1]
            prev_lb = lower_band[-1]

            if closes[i + 1] <= prev_ub:
                ub = min(ub, prev_ub)
            upper_band.append(ub)

            if closes[i + 1] >= prev_lb:
                lb = max(lb, prev_lb)
            lower_band.append(lb)

        upper_band.reverse()
        lower_band.reverse()

        # Direction and value based on close vs band
        close = closes[-1]
        ub = upper_band[-1]
        lb = lower_band[-1]

        # Determine which band was most recently crossed
        # Simple approach: if close > previous upper band, bullish; if close < previous lower band, bearish
        prev_close = closes[-2]
        prev_ub = upper_band[-2]
        prev_lb = lower_band[-2]

        # Start with previous direction
        prev_supertrend = prev_ub if prev_close <= prev_ub else prev_lb
        prev_direction = -1 if prev_close <= prev_ub else 1

        if prev_direction == 1:
            # Was bullish — check if bearish flip
            if close <= lb:
                direction = -1
                value = ub
            else:
                direction = 1
                value = max(lb, prev_lb)
        else:
            # Was bearish — check if bullish flip
            if close >= ub:
                direction = 1
                value = lb
            else:
                direction = -1
                value = min(ub, prev_ub)

        return direction, value

    @staticmethod
    def calc_adx(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14,
    ) -> float | None:
        """Average Directional Index — trend strength indicator."""
        n = len(closes)
        if n < period + 1:
            return None

        # Calculate True Range
        tr_values: list[float] = []
        dm_plus: list[float] = []
        dm_minus: list[float] = []

        for i in range(1, n):
            high = highs[i]
            low = lows[i]
            prev_high = highs[i - 1]
            prev_low = lows[i - 1]
            prev_close = closes[i - 1]

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
            tr_values.append(tr)

            up_move = high - prev_high
            down_move = prev_low - low

            if up_move > down_move and up_move > 0:
                dm_plus.append(up_move)
            else:
                dm_plus.append(0.0)

            if down_move > up_move and down_move > 0:
                dm_minus.append(down_move)
            else:
                dm_minus.append(0.0)

        # Smooth with Wilder's method (EMA-like with 1/period factor)
        atr_smooth = sum(tr_values[:period]) / period
        dm_plus_smooth = sum(dm_plus[:period]) / period
        dm_minus_smooth = sum(dm_minus[:period]) / period

        dx_values: list[float] = []
        for i in range(period, len(tr_values)):
            atr_smooth = (atr_smooth * (period - 1) + tr_values[i]) / period
            dm_plus_smooth = (dm_plus_smooth * (period - 1) + dm_plus[i]) / period
            dm_minus_smooth = (dm_minus_smooth * (period - 1) + dm_minus[i]) / period

            if atr_smooth == 0:
                dx_values.append(0.0)
            else:
                di_plus = 100.0 * dm_plus_smooth / atr_smooth
                di_minus = 100.0 * dm_minus_smooth / atr_smooth
                di_sum = di_plus + di_minus
                if di_sum == 0:
                    dx_values.append(0.0)
                else:
                    dx_values.append(100.0 * abs(di_plus - di_minus) / di_sum)

        if not dx_values:
            return None

        # ADX = smoothed DX
        adx = sum(dx_values[:period]) / period if len(dx_values) >= period else sum(dx_values) / len(dx_values)
        for i in range(period, len(dx_values)):
            adx = (adx * (period - 1) + dx_values[i]) / period

        return adx

    # ── Momentum Indicators ────────────────────────────────────────────────────

    @staticmethod
    def calc_rsi(data: list[float], period: int = 14) -> float | None:
        """Relative Strength Index — Wilder's smoothing method."""
        if len(data) < period + 1:
            return None

        gains: list[float] = []
        losses: list[float] = []

        for i in range(1, len(data)):
            diff = data[i] - data[i - 1]
            if diff > 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))

        # Initial average
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Wilder's smoothing for remaining
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi

    @staticmethod
    def calc_macd(
        data: list[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[float | None, float | None, float | None]:
        """MACD — Moving Average Convergence Divergence.

        Returns (macd_line, signal_line, histogram).
        """
        if len(data) < slow + signal:
            return None, None, None

        # Calculate EMA-12 and EMA-26
        ema_fast = TechnicalAnalysisService._calc_ema_single(data, fast)
        ema_slow = TechnicalAnalysisService._calc_ema_single(data, slow)

        if ema_fast is None or ema_slow is None:
            return None, None, None

        # Build MACD line for the last 'signal' periods
        macd_values: list[float] = []
        for i in range(slow - 1, len(data)):
            ef = TechnicalAnalysisService._calc_ema_single(data[:i + 1], fast)
            es = TechnicalAnalysisService._calc_ema_single(data[:i + 1], slow)
            if ef is not None and es is not None:
                macd_values.append(ef - es)

        if len(macd_values) < signal:
            return ema_fast - ema_slow, None, None

        macd_line = macd_values[-1]

        # Signal line = EMA-9 of MACD values
        signal_line = TechnicalAnalysisService.calc_ema(macd_values, signal)
        if signal_line is None:
            return macd_line, None, None

        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def calc_stochastic(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        k_period: int = 14,
        d_period: int = 3,
    ) -> tuple[float | None, float | None]:
        """Stochastic Oscillator — returns (%K, %D)."""
        if len(closes) < k_period:
            return None, None

        # Calculate %K values
        k_values: list[float] = []
        for i in range(k_period - 1, len(closes)):
            window_high = max(highs[i - k_period + 1 : i + 1])
            window_low = min(lows[i - k_period + 1 : i + 1])
            if window_high == window_low:
                k_values.append(50.0)
            else:
                k_values.append(
                    100.0 * (closes[i] - window_low) / (window_high - window_low)
                )

        if not k_values:
            return None, None

        k = k_values[-1]

        # %D = SMA of %K
        if len(k_values) < d_period:
            return k, None

        d = sum(k_values[-d_period:]) / d_period
        return k, d

    # ── Volatility Indicators ──────────────────────────────────────────────────

    @staticmethod
    def calc_atr(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14,
    ) -> float | None:
        """Average True Range — Wilder's smoothing method."""
        n = len(closes)
        if n < period + 1:
            return None

        tr_values: list[float] = []
        for i in range(1, n):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            tr_values.append(tr)

        # Initial ATR = SMA of first 'period' TR values
        atr = sum(tr_values[:period]) / period

        # Wilder's smoothing
        for i in range(period, len(tr_values)):
            atr = (atr * (period - 1) + tr_values[i]) / period

        return atr

    @staticmethod
    def calc_bollinger_bands(
        data: list[float],
        period: int = 20,
        num_std: float = 2.0,
    ) -> tuple[float | None, float | None, float | None]:
        """Bollinger Bands — returns (upper, middle, lower)."""
        if len(data) < period:
            return None, None, None

        middle = sum(data[-period:]) / period

        # Population standard deviation
        variance = sum((x - middle) ** 2 for x in data[-period:]) / period
        std = variance ** 0.5

        upper = middle + num_std * std
        lower = middle - num_std * std

        return upper, middle, lower

    # ── Volume Indicators ──────────────────────────────────────────────────────

    @staticmethod
    def calc_vwap(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        volumes: list[int],
    ) -> float | None:
        """Volume Weighted Average Price (cumulative from start of data)."""
        if not closes or not volumes:
            return None

        # Typical price = (high + low + close) / 3
        total_pv = 0.0
        total_vol = 0

        for h, l, c, v in zip(highs, lows, closes, volumes):
            typical_price = (h + l + c) / 3.0
            total_pv += typical_price * v
            total_vol += v

        if total_vol == 0:
            return None

        return total_pv / total_vol

    # ── Price Action ───────────────────────────────────────────────────────────

    @staticmethod
    def calc_support_resistance(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        lookback: int = 20,
    ) -> tuple[list[float], list[float]]:
        """Detect support and resistance levels using pivot-based method.

        Uses local highs as resistance and local lows as support, then clusters
        nearby levels and returns the top clusters.
        """
        n = len(closes)
        if n < lookback:
            return [], []

        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]

        # Find local maxima (resistance candidates)
        resistance_candidates: list[float] = []
        for i in range(2, len(recent_highs) - 2):
            if (
                recent_highs[i] > recent_highs[i - 1]
                and recent_highs[i] > recent_highs[i - 2]
                and recent_highs[i] > recent_highs[i + 1]
                and recent_highs[i] > recent_highs[i + 2]
            ):
                resistance_candidates.append(recent_highs[i])

        # Find local minima (support candidates)
        support_candidates: list[float] = []
        for i in range(2, len(recent_lows) - 2):
            if (
                recent_lows[i] < recent_lows[i - 1]
                and recent_lows[i] < recent_lows[i - 2]
                and recent_lows[i] < recent_lows[i + 1]
                and recent_lows[i] < recent_lows[i + 2]
            ):
                support_candidates.append(recent_lows[i])

        # Cluster nearby levels (within 0.1% of price)
        def cluster_levels(levels: list[float]) -> list[float]:
            if not levels:
                return []
            sorted_levels = sorted(set(levels))
            clusters: list[list[float]] = []
            current_cluster = [sorted_levels[0]]

            for level in sorted_levels[1:]:
                if current_cluster and abs(level - current_cluster[-1]) / current_cluster[-1] < 0.001:
                    current_cluster.append(level)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [level]
            clusters.append(current_cluster)

            return [round(sum(c) / len(c), 5) for c in clusters]

        resistance = cluster_levels(resistance_candidates)
        support = cluster_levels(support_candidates)

        # Limit to top levels
        return support[:3], resistance[:3]

    @staticmethod
    def calc_swing_high(highs: list[float], lookback: int = 5) -> float | None:
        """Detect the most recent swing high (local maximum)."""
        if len(highs) < lookback * 2 + 1:
            return None

        # Look at the middle of the lookback window
        window = highs[-lookback * 2 - 1:]
        center_idx = lookback
        center_val = window[center_idx]

        left_max = max(window[:center_idx])
        right_max = max(window[center_idx + 1:])

        if center_val > left_max and center_val > right_max:
            return center_val

        # Try one more step back
        if len(highs) >= lookback * 2 + 5:
            window2 = highs[-lookback * 2 - 5:]
            for offset in range(0, 3):
                ci = lookback + offset
                cv = window2[ci]
                lm = max(window2[:ci])
                rm = max(window2[ci + 1:ci + lookback + 1])
                if cv > lm and cv > rm:
                    return cv

        return None

    @staticmethod
    def calc_swing_low(lows: list[float], lookback: int = 5) -> float | None:
        """Detect the most recent swing low (local minimum)."""
        if len(lows) < lookback * 2 + 1:
            return None

        window = lows[-lookback * 2 - 1:]
        center_idx = lookback
        center_val = window[center_idx]

        left_min = min(window[:center_idx])
        right_min = min(window[center_idx + 1:])

        if center_val < left_min and center_val < right_min:
            return center_val

        if len(lows) >= lookback * 2 + 5:
            window2 = lows[-lookback * 2 - 5:]
            for offset in range(0, 3):
                ci = lookback + offset
                cv = window2[ci]
                lm = min(window2[:ci])
                rm = min(window2[ci + 1:ci + lookback + 1])
                if cv < lm and cv < rm:
                    return cv

        return None

    @staticmethod
    def calc_fibonacci(
        highs: list[float],
        lows: list[float],
        lookback: int = 50,
    ) -> dict[float, float] | None:
        """Calculate Fibonacci retracement levels.

        Uses the highest high and lowest low in the lookback window.
        Returns dict mapping ratio to price level.
        """
        if len(highs) < lookback or len(lows) < lookback:
            return None

        window_highs = highs[-lookback:]
        window_lows = lows[-lookback:]

        highest = max(window_highs)
        lowest = min(window_lows)

        if highest == lowest:
            return None

        diff = highest - lowest

        return {
            0.0: round(lowest, 5),
            0.236: round(lowest + 0.236 * diff, 5),
            0.382: round(lowest + 0.382 * diff, 5),
            0.5: round(lowest + 0.5 * diff, 5),
            0.618: round(lowest + 0.618 * diff, 5),
            0.786: round(lowest + 0.786 * diff, 5),
            1.0: round(highest, 5),
        }

    # ── Private helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _calc_ema_single(data: list[float], period: int) -> float | None:
        """Calculate EMA starting from the beginning — used by MACD."""
        if len(data) < period or period <= 0:
            return None
        multiplier = 2.0 / (period + 1)
        ema = sum(data[:period]) / period
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
