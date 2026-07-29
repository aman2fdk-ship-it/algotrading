"""Unit tests for Technical Indicator calculations.

Verifies each indicator method with known input/output pairs.
"""

import math
import pytest
from datetime import datetime, timezone

from app.models.candle import Candle
from app.services.technical_analysis import TechnicalAnalysisService


def make_candle(
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int = 100,
    ts_offset: int = 0,
) -> Candle:
    """Helper to create a Candle with a fixed timestamp offset."""
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return Candle(
        symbol="EURUSD",
        timeframe="H1",
        timestamp=datetime.fromtimestamp(base.timestamp() + ts_offset * 3600, tz=timezone.utc),
        open=open_price,
        high=high,
        low=low,
        close=close,
        tick_volume=volume,
    )


def make_candles(prices: list[tuple[float, float, float, float]]) -> list[Candle]:
    """Create candles from a list of (open, high, low, close) tuples."""
    return [
        make_candle(o, h, l, c, ts_offset=i)
        for i, (o, h, l, c) in enumerate(prices)
    ]


# ── Helper test data ──────────────────────────────────────────────────────────

# Simple uptrend: 10 candles where close = 1.0 + i*0.01
UPTREND_10 = [
    (1.000, 1.002, 0.999, 1.001),
    (1.001, 1.003, 1.000, 1.002),
    (1.002, 1.004, 1.001, 1.003),
    (1.003, 1.005, 1.002, 1.004),
    (1.004, 1.006, 1.003, 1.005),
    (1.005, 1.007, 1.004, 1.006),
    (1.006, 1.008, 1.005, 1.007),
    (1.007, 1.009, 1.006, 1.008),
    (1.008, 1.010, 1.007, 1.009),
    (1.009, 1.011, 1.008, 1.010),
]

# 30 candles for longer-period indicators
UPTREND_30 = [(1.0 + i * 0.002, 1.0 + i * 0.002 + 0.001,
                1.0 + i * 0.002 - 0.001, 1.0 + i * 0.002 + 0.0005) for i in range(30)]

# Sideways market (low volatility) — easy to verify RSI ~50
SIDEWAYS_20 = [
    (1.100, 1.101, 1.099, 1.100),
    (1.100, 1.102, 1.098, 1.099),
    (1.099, 1.101, 1.098, 1.101),
    (1.101, 1.102, 1.099, 1.100),
    (1.100, 1.101, 1.099, 1.100),
    (1.100, 1.102, 1.098, 1.101),
    (1.101, 1.102, 1.100, 1.100),
    (1.100, 1.101, 1.099, 1.100),
    (1.100, 1.102, 1.098, 1.099),
    (1.099, 1.100, 1.098, 1.100),
    (1.100, 1.101, 1.099, 1.100),
    (1.100, 1.102, 1.098, 1.101),
    (1.101, 1.102, 1.100, 1.100),
    (1.100, 1.101, 1.099, 1.100),
    (1.100, 1.102, 1.098, 1.099),
    (1.099, 1.100, 1.098, 1.100),
    (1.100, 1.101, 1.099, 1.100),
    (1.100, 1.102, 1.098, 1.101),
    (1.101, 1.102, 1.100, 1.100),
    (1.100, 1.101, 1.099, 1.100),
]


class TestSMA:
    def test_sma_basic(self):
        result = TechnicalAnalysisService.calc_sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert result == pytest.approx(4.0)  # (3+4+5)/3

    def test_sma_insufficient_data(self):
        result = TechnicalAnalysisService.calc_sma([1.0, 2.0], 3)
        assert result is None

    def test_sma_zero_period(self):
        result = TechnicalAnalysisService.calc_sma([1.0, 2.0], 0)
        assert result is None


class TestEMA:
    def test_ema_known_values(self):
        # Manual calculation for EMA-3 on [1,2,3,4,5]
        # SMA of first 3: (1+2+3)/3 = 2.0
        # multiplier = 2/(3+1) = 0.5
        # EMA after 4: (4 - 2.0) * 0.5 + 2.0 = 3.0
        # EMA after 5: (5 - 3.0) * 0.5 + 3.0 = 4.0
        result = TechnicalAnalysisService.calc_ema([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert result == pytest.approx(4.0)

    def test_ema_insufficient_data(self):
        result = TechnicalAnalysisService.calc_ema([1.0, 2.0], 10)
        assert result is None

    def test_ema_200_requires_200_points(self):
        data = list(range(199))
        result = TechnicalAnalysisService.calc_ema(data, 200)
        assert result is None

        data = list(range(200))
        result = TechnicalAnalysisService.calc_ema(data, 200)
        assert result is not None


class TestRSI:
    def test_rsi_all_gains(self):
        # Strictly increasing — all gains, no losses => RSI = 100
        data = [1.0 + i * 0.1 for i in range(20)]
        result = TechnicalAnalysisService.calc_rsi(data, 14)
        assert result == pytest.approx(100.0)

    def test_rsi_all_losses(self):
        # Strictly decreasing — all losses, no gains => RSI = 0
        data = [20.0 - i * 0.1 for i in range(20)]
        result = TechnicalAnalysisService.calc_rsi(data, 14)
        assert result == pytest.approx(0.0)

    def test_rsi_sideways(self):
        # Very tight range — RSI should be close to 50
        data = [1.100 + (i % 3 - 1) * 0.0001 for i in range(20)]
        result = TechnicalAnalysisService.calc_rsi(data, 14)
        assert 40 < result < 60  # type: ignore[operator]

    def test_rsi_insufficient_data(self):
        result = TechnicalAnalysisService.calc_rsi([1.0, 2.0], 14)
        assert result is None


class TestMACD:
    def test_macd_known_values(self):
        # Constant data should give MACD = 0, signal = 0, histogram = 0
        data = [1.0] * 50
        macd, signal, hist = TechnicalAnalysisService.calc_macd(data)
        assert macd == pytest.approx(0.0, abs=1e-9)
        if signal is not None:
            assert signal == pytest.approx(0.0, abs=1e-9)
        if hist is not None:
            assert hist == pytest.approx(0.0, abs=1e-9)

    def test_macd_insufficient_data(self):
        data = [1.0] * 20  # Need 26 + 9 = 35 minimum
        macd, signal, hist = TechnicalAnalysisService.calc_macd(data)
        assert macd is None
        assert signal is None
        assert hist is None

    def test_macd_basic(self):
        # Non-constant data should give non-zero MACD
        data = [1.0 + i * 0.01 for i in range(50)]
        macd, signal, hist = TechnicalAnalysisService.calc_macd(data)
        assert macd is not None
        assert signal is not None
        assert hist is not None


class TestStochastic:
    def test_stochastic_high_close(self):
        # Close = high => %K = 100
        highs = [10.0 + i for i in range(20)]
        lows = [9.0 + i for i in range(20)]
        closes = [10.0 + i for i in range(20)]  # close = high
        k, d = TechnicalAnalysisService.calc_stochastic(highs, lows, closes)
        assert k == pytest.approx(100.0)
        assert d == pytest.approx(100.0)

    def test_stochastic_low_close(self):
        # Close = low in every window => %K = 0
        # Use flat data: highs constant, lows = closes = constant
        highs = [10.0] * 20
        lows = [9.0] * 20
        closes = [9.0] * 20  # close = low always
        k, d = TechnicalAnalysisService.calc_stochastic(highs, lows, closes)
        assert k == pytest.approx(0.0)
        assert d == pytest.approx(0.0)

    def test_stochastic_insufficient_data(self):
        k, d = TechnicalAnalysisService.calc_stochastic([1.0, 2.0], [1.0, 2.0], [1.0, 2.0])
        assert k is None
        assert d is None


class TestATR:
    def test_atr_known_values(self):
        # Classic Wilder ATR example with constant true range
        highs = [10.0 + i * 0.5 for i in range(20)]
        lows = [9.0 + i * 0.5 for i in range(20)]
        closes = [9.5 + i * 0.5 for i in range(20)]
        # True range is consistently 1.0 (high - low)
        result = TechnicalAnalysisService.calc_atr(highs, lows, closes, 14)
        assert result == pytest.approx(1.0, abs=0.1)

    def test_atr_insufficient_data(self):
        result = TechnicalAnalysisService.calc_atr([1.0, 2.0], [1.0, 2.0], [1.0, 2.0], 14)
        assert result is None


class TestBollingerBands:
    def test_bb_constant_data(self):
        # All same price => std = 0 => upper = middle = lower
        data = [1.0] * 25
        upper, middle, lower = TechnicalAnalysisService.calc_bollinger_bands(data)
        assert upper == pytest.approx(1.0)
        assert middle == pytest.approx(1.0)
        assert lower == pytest.approx(1.0)

    def test_bb_insufficient_data(self):
        data = [1.0] * 15  # Need 20
        upper, middle, lower = TechnicalAnalysisService.calc_bollinger_bands(data)
        assert upper is None
        assert middle is None
        assert lower is None

    def test_bb_known_values(self):
        # Data: [1,2,3,...,20] => mean = 10.5, range of 20 values
        data = [float(i) for i in range(1, 21)]
        upper, middle, lower = TechnicalAnalysisService.calc_bollinger_bands(data)
        assert middle == pytest.approx(10.5)
        # Population std of [1..20] = sqrt((n^2-1)/12) = sqrt(399/12) ≈ 5.766
        expected_std = math.sqrt((400 - 1) / 12)
        assert upper == pytest.approx(10.5 + 2 * expected_std)
        assert lower == pytest.approx(10.5 - 2 * expected_std)


class TestADX:
    def test_adx_insufficient_data(self):
        result = TechnicalAnalysisService.calc_adx([1.0]*5, [1.0]*5, [1.0]*5, 14)
        assert result is None

    def test_adx_basic(self):
        # 30 candles with some movement
        n = 30
        highs = [100.0 + i + (i % 3) * 0.1 for i in range(n)]
        lows = [99.0 + i - (i % 2) * 0.1 for i in range(n)]
        closes = [99.5 + i + (i % 4) * 0.05 for i in range(n)]
        result = TechnicalAnalysisService.calc_adx(highs, lows, closes, 14)
        assert result is not None
        assert 0 <= result <= 100


class TestVWAP:
    def test_vwap_basic(self):
        highs = [10.0] * 5
        lows = [9.0] * 5
        closes = [9.5] * 5
        volumes = [100] * 5
        # Typical price = (10+9+9.5)/3 = 9.5
        result = TechnicalAnalysisService.calc_vwap(highs, lows, closes, volumes)
        assert result == pytest.approx(9.5)

    def test_vwap_weighted(self):
        highs = [10.0, 10.0]
        lows = [9.0, 9.0]
        closes = [9.5, 9.5]
        volumes = [100, 200]
        # tp = 9.5, pv = 9.5*100 + 9.5*200 = 2850, total_vol = 300, vwap = 9.5
        result = TechnicalAnalysisService.calc_vwap(highs, lows, closes, volumes)
        assert result == pytest.approx(9.5)

    def test_vwap_empty(self):
        result = TechnicalAnalysisService.calc_vwap([], [], [], [])
        assert result is None

    def test_vwap_zero_volume(self):
        result = TechnicalAnalysisService.calc_vwap([10.0], [9.0], [9.5], [0])
        assert result is None


class TestSuperTrend:
    def test_supertrend_insufficient_data(self):
        direction, value = TechnicalAnalysisService.calc_supertrend(
            [1.0]*5, [1.0]*5, [1.0]*5
        )
        assert direction is None
        assert value is None

    def test_supertrend_basic(self):
        n = 30
        highs = [100.0 + i * 0.1 + 0.5 for i in range(n)]
        lows = [100.0 + i * 0.1 - 0.5 for i in range(n)]
        closes = [100.0 + i * 0.1 + (i % 3 - 1) * 0.2 for i in range(n)]
        direction, value = TechnicalAnalysisService.calc_supertrend(highs, lows, closes)
        assert direction in (1, -1)
        assert value is not None
        assert value > 0


class TestSupportResistance:
    def test_support_resistance_basic(self):
        highs = [100.0 + i * 0.1 + (i % 5) * 0.5 for i in range(30)]
        lows = [99.0 + i * 0.1 - (i % 4) * 0.3 for i in range(30)]
        closes = [99.5 + i * 0.1 for i in range(30)]
        support, resistance = TechnicalAnalysisService.calc_support_resistance(
            highs, lows, closes
        )
        assert isinstance(support, list)
        assert isinstance(resistance, list)

    def test_support_resistance_insufficient_data(self):
        support, resistance = TechnicalAnalysisService.calc_support_resistance(
            [1.0]*5, [1.0]*5, [1.0]*5, lookback=20
        )
        assert support == []
        assert resistance == []


class TestSwingHighLow:
    def test_swing_high_basic(self):
        # Create a clear swing high at the center of the last 11 elements
        # lookback=5 => need lookback*2+1 = 11 elements minimum
        # Peak must be at center_idx=5 within the last 11
        data = [1.0, 1.0] + [1.0, 1.0, 1.0, 1.0, 1.0, 3.0, 1.0, 1.0, 1.0, 1.0, 1.0]
        # Last 11: [1.0, 1.0, 1.0, 1.0, 1.0, 3.0, 1.0, 1.0, 1.0, 1.0, 1.0]
        # center_idx=5 -> value 3.0, left_max=1.0, right_max=1.0
        result = TechnicalAnalysisService.calc_swing_high(data, lookback=5)
        assert result == pytest.approx(3.0)

    def test_swing_low_basic(self):
        data = [3.0, 3.0] + [3.0, 3.0, 3.0, 3.0, 3.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0]
        result = TechnicalAnalysisService.calc_swing_low(data, lookback=5)
        assert result == pytest.approx(1.0)

    def test_swing_high_insufficient_data(self):
        result = TechnicalAnalysisService.calc_swing_high([1.0]*5, lookback=5)
        assert result is None


class TestFibonacci:
    def test_fibonacci_basic(self):
        highs = [100.0 + i * 0.1 for i in range(60)]
        lows = [90.0 + i * 0.1 for i in range(60)]
        result = TechnicalAnalysisService.calc_fibonacci(highs, lows, lookback=50)
        assert result is not None
        assert 0.236 in result
        assert 0.382 in result
        assert 0.5 in result
        assert 0.618 in result
        assert 0.786 in result
        # Levels should be between min and max
        max_high = max(highs[-50:])
        min_low = min(lows[-50:])
        for level in result.values():
            assert min_low <= level <= max_high

    def test_fibonacci_insufficient_data(self):
        result = TechnicalAnalysisService.calc_fibonacci([1.0]*5, [1.0]*5, lookback=50)
        assert result is None

    def test_fibonacci_flat_market(self):
        # All same highs and lows
        data_h = [1.0] * 60
        data_l = [1.0] * 60
        result = TechnicalAnalysisService.calc_fibonacci(data_h, data_l, lookback=50)
        assert result is None


class TestCalculateAll:
    def test_calculate_all_returns_indicator(self):
        candles = make_candles(UPTREND_30)
        service = TechnicalAnalysisService()
        result = service.calculate_all(candles, "EURUSD", "H1")
        assert result is not None
        assert result.symbol == "EURUSD"
        assert result.timeframe == "H1"
        # Should have all major indicators
        assert result.rsi is not None
        assert result.atr is not None
        assert result.ema_20 is not None

    def test_calculate_all_empty_candles(self):
        service = TechnicalAnalysisService()
        result = service.calculate_all([], "EURUSD", "H1")
        assert result is None

    def test_calculate_all_with_small_data(self):
        # Only 5 candles — many indicators will be None
        candles = make_candles(UPTREND_10[:5])
        service = TechnicalAnalysisService()
        result = service.calculate_all(candles, "EURUSD", "H1")
        assert result is not None
        # Short-period indicators might not work with only 5 candles
        # But the method should not crash
        assert result.symbol == "EURUSD"
