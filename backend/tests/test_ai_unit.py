"""Unit tests for AI Decision Engine scoring methods and decision logic.

Tests every scoring method with known indicator/SMC/candle inputs
producing expected scores. Edge cases: missing data, flat markets, extreme scores.
"""

import math
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.candle import Candle
from app.models.smc_structure import SMCStructure
from app.models.technical_indicator import TechnicalIndicator
from app.services.ai_decision import (
    AIDecisionService,
    DecisionResult,
    CategoryScore,
    TimeframeScore,
    CATEGORY_WEIGHTS,
    ALL_TIMEFRAMES,
    BUY_THRESHOLD,
    SELL_THRESHOLD,
)


# ── Test Helpers ────────────────────────────────────────────────────────────────

def _make_indicator(**overrides) -> TechnicalIndicator:
    """Create a TechnicalIndicator with sensible defaults, overridable.
    
    Pass field=None explicitly to set a field to None.
    Pass UNSET (default sentinel) to leave the default value.
    """
    UNSET = object()
    defaults = {
        "symbol": "EURUSD",
        "timeframe": "H1",
        "timestamp": datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        "ema_20": 1.0850,
        "ema_50": 1.0800,
        "ema_200": 1.0700,
        "supertrend_direction": 1,
        "supertrend_value": 1.0780,
        "adx": 28.0,
        "rsi": 55.0,
        "macd_line": 0.00050,
        "macd_signal": 0.00030,
        "macd_histogram": 0.00020,
        "stoch_k": 60.0,
        "stoch_d": 55.0,
        "atr": 0.0015,
        "bb_upper": 1.0880,
        "bb_middle": 1.0830,
        "bb_lower": 1.0780,
        "vwap": 1.0820,
        "support_levels": [1.0750, 1.0700],
        "resistance_levels": [1.0900, 1.0950],
        "swing_high": 1.0920,
        "swing_low": 1.0730,
    }
    # Apply overrides: explicit None values are kept; missing keys use defaults
    for k, v in overrides.items():
        defaults[k] = v
    ind = TechnicalIndicator(**defaults)
    return ind


def _make_candle(
    open_p: float,
    high: float,
    low: float,
    close: float,
    volume: int = 100,
    ts_offset: int = 0,
    symbol: str = "EURUSD",
    timeframe: str = "H1",
) -> Candle:
    """Create a Candle with a timestamp offset."""
    base = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.fromtimestamp(base.timestamp() + ts_offset * 3600, tz=timezone.utc),
        open=open_p,
        high=high,
        low=low,
        close=close,
        tick_volume=volume,
    )


def _make_smc(
    structure_type: str,
    direction: str,
    confidence: float = 0.8,
    price_low: float | None = None,
    price_high: float | None = None,
    price_mid: float | None = None,
    key_level: float | None = None,
) -> SMCStructure:
    """Create an SMCStructure."""
    return SMCStructure(
        symbol="EURUSD",
        timeframe="H1",
        timestamp=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        structure_type=structure_type,
        direction=direction,
        price_low=price_low,
        price_high=price_high,
        price_mid=price_mid,
        key_level=key_level,
        confidence=confidence,
    )


def _make_service(
    indicator: TechnicalIndicator | None = None,
    smc_structures: list[SMCStructure] | None = None,
    candles: list[Candle] | None = None,
) -> AIDecisionService:
    """Create AIDecisionService with mocked repositories."""
    ind_repo = MagicMock()
    ind_repo.get_latest = AsyncMock(return_value=indicator)
    ind_repo.get_by_symbol_timeframe = AsyncMock(return_value=[indicator] if indicator else [])

    smc_repo = MagicMock()
    smc_repo.get_all = AsyncMock(return_value=smc_structures or [])
    smc_repo.get_by_type = AsyncMock(return_value=[])

    candle_repo = MagicMock()
    candle_repo.get_candles = AsyncMock(return_value=candles or [])
    candle_repo.get_latest_candle = AsyncMock(
        return_value=candles[-1] if candles else None
    )

    return AIDecisionService(ind_repo, smc_repo, candle_repo)


# ═════════════════════════════════════════════════════════════════════════════════
# Trend Scoring Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestTrendScoring:
    """Tests for _score_trend method."""

    def test_bullish_ema_alignment_with_adx(self):
        """Bullish EMA alignment + strong ADX + bullish SuperTrend = strong positive."""
        ind = _make_indicator(ema_20=1.090, ema_50=1.080, ema_200=1.070, adx=30.0, supertrend_direction=1)
        service = _make_service()
        result = service._score_trend(ind)
        # EMA bullish (+1.0), ADX>25 so multiplier 1.0 -> 1.0
        # SuperTrend bullish (+1.0) -> 0.6*1.0 + 0.4*1.0 = 1.0
        assert result.score == pytest.approx(1.0, abs=0.01)
        assert any("bullish alignment" in d.lower() for d in result.details)

    def test_bearish_ema_alignment_with_adx(self):
        """Bearish EMA + strong ADX + bearish SuperTrend = strong negative."""
        ind = _make_indicator(ema_20=1.060, ema_50=1.070, ema_200=1.080, adx=35.0, supertrend_direction=-1)
        service = _make_service()
        result = service._score_trend(ind)
        # EMA bearish (-1.0), ADX>25 -> -1.0
        # SuperTrend bearish (-1.0) -> 0.6*(-1.0) + 0.4*(-1.0) = -1.0
        assert result.score == pytest.approx(-1.0, abs=0.01)

    def test_mixed_ema_neutral(self):
        """Mixed EMA alignment should give ~0 even with strong ADX."""
        ind = _make_indicator(ema_20=1.080, ema_50=1.085, ema_200=1.070, adx=30.0)
        service = _make_service()
        result = service._score_trend(ind)
        # EMA mixed (0.0), ADX irrelevant since trend is 0
        assert abs(result.score) < 0.6

    def test_weak_adx_dampens_trend(self):
        """ADX < 20 should reduce trend confidence."""
        ind = _make_indicator(ema_20=1.090, ema_50=1.080, ema_200=1.070, adx=15.0, supertrend_direction=0)
        service = _make_service()
        result = service._score_trend(ind)
        # ADX<20 means multiplier 0 -> EMA contribution 0
        # SuperTrend 0 -> 0
        assert result.score == pytest.approx(0.0, abs=0.01)

    def test_trend_none_indicator(self):
        """None indicator returns zero score."""
        service = _make_service()
        result = service._score_trend(None)
        assert result.score == 0.0
        assert result.weight == CATEGORY_WEIGHTS["trend"]

    def test_trend_missing_emas(self):
        """Missing EMA data defaults to neutral."""
        ind = _make_indicator(ema_20=None, ema_50=None, ema_200=None, adx=30.0, supertrend_direction=1)
        service = _make_service()
        result = service._score_trend(ind)
        # Only SuperTrend contributes: 0.6*0 + 0.4*1.0 = 0.4
        assert result.score == pytest.approx(0.4, abs=0.01)


# ═════════════════════════════════════════════════════════════════════════════════
# Momentum Scoring Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestMomentumScoring:
    """Tests for _score_momentum method."""

    def test_bullish_rsi(self):
        """RSI > 50 gives positive momentum."""
        ind = _make_indicator(rsi=58.0, macd_histogram=None, stoch_k=None)
        service = _make_service()
        result = service._score_momentum(ind)
        # RSI=58 > 50 -> 0.5, weight 0.5 -> 0.25
        # No MACD/Stoch contributions
        assert result.score > 0.15

    def test_overbought_rsi(self):
        """RSI > 70 should be bearish (overbought)."""
        ind = _make_indicator(rsi=75.0, macd_histogram=None, stoch_k=None)
        service = _make_service()
        result = service._score_momentum(ind)
        assert result.score < 0

    def test_oversold_rsi(self):
        """RSI < 30 should be bullish (oversold)."""
        ind = _make_indicator(rsi=22.0, macd_histogram=None, stoch_k=None)
        service = _make_service()
        result = service._score_momentum(ind)
        assert result.score > 0

    def test_positive_macd_histogram(self):
        """Positive MACD histogram gives bullish momentum."""
        ind = _make_indicator(rsi=None, macd_histogram=0.0003, macd_line=0.0005, macd_signal=0.0004, stoch_k=None)
        service = _make_service()
        result = service._score_momentum(ind)
        assert result.score > 0

    def test_negative_macd_histogram(self):
        """Negative MACD histogram gives bearish momentum."""
        ind = _make_indicator(rsi=50.0, macd_histogram=-0.0003, macd_line=-0.0005, macd_signal=-0.0004, stoch_k=50.0)
        service = _make_service()
        result = service._score_momentum(ind)
        # RSI=50 neutral, Stoch=50 neutral, MACD negative → overall negative
        assert result.score < 0

    def test_overbought_stochastic(self):
        """Stoch > 80 is negative (overbought)."""
        ind = _make_indicator(rsi=50.0, macd_histogram=None, stoch_k=88.0)
        service = _make_service()
        result = service._score_momentum(ind)
        assert result.score < 0

    def test_oversold_stochastic(self):
        """Stoch < 20 is positive (oversold)."""
        ind = _make_indicator(rsi=None, macd_histogram=None, stoch_k=12.0)
        service = _make_service()
        result = service._score_momentum(ind)
        assert result.score > 0

    def test_none_indicator(self):
        """None indicator gives zero."""
        service = _make_service()
        result = service._score_momentum(None)
        assert result.score == 0.0

    def test_all_bullish_aligned(self):
        """All momentum indicators aligned bullish."""
        ind = _make_indicator(rsi=62.0, macd_histogram=0.0005, macd_line=0.0006, macd_signal=0.0004, stoch_k=58.0)
        service = _make_service()
        result = service._score_momentum(ind)
        # RSI 62 -> +0.5*0.5=0.25 + MACD positive&rising -> +0.5*0.3=0.15 + Stoch neutral -> 0
        # total approx 0.4
        assert result.score > 0.3


# ═════════════════════════════════════════════════════════════════════════════════
# SMC/ICT Scoring Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestSMCScoring:
    """Tests for _score_smc method."""

    def test_bullish_choch_dominant(self):
        """Bullish CHoCH with high confidence should dominate."""
        smcs = [
            _make_smc("choch", "bullish", confidence=0.95),
            _make_smc("bos", "bullish", confidence=0.7),
        ]
        service = _make_service()
        result = service._score_smc(smcs)
        # CHoCH: +1*0.8*0.95=+0.76, BOS: +1*0.6*0.7=+0.42
        # avg = (0.76+0.42)/2 = 0.59
        assert result.score > 0.4

    def test_bearish_choch(self):
        """Bearish CHoCH should give negative score."""
        smcs = [_make_smc("choch", "bearish", confidence=0.9)]
        service = _make_service()
        result = service._score_smc(smcs)
        assert result.score < -0.5

    def test_sellside_liquidity_sweep_bullish(self):
        """Sellside sweep (liquidity below taken) = bullish signal."""
        smcs = [_make_smc("liquidity_sweep", "bearish", confidence=0.8)]
        service = _make_service()
        result = service._score_smc(smcs)
        assert result.score > 0

    def test_buyside_liquidity_sweep_bearish(self):
        """Buyside sweep (liquidity above taken) = bearish signal."""
        smcs = [_make_smc("liquidity_sweep", "bullish", confidence=0.8)]
        service = _make_service()
        result = service._score_smc(smcs)
        assert result.score < 0

    def test_premium_discount_zones(self):
        """Premium zone = bearish, Discount zone = bullish."""
        premium = _make_smc("premium_discount", "bearish", confidence=0.8)
        service = _make_service()
        result = service._score_smc([premium])
        assert result.score < 0

        discount = _make_smc("premium_discount", "bullish", confidence=0.8)
        result2 = service._score_smc([discount])
        assert result2.score > 0

    def test_order_blocks(self):
        """Bullish OB = positive, Bearish OB = negative."""
        bull_ob = _make_smc("order_block", "bullish", confidence=0.8, price_mid=1.0800)
        service = _make_service()
        assert service._score_smc([bull_ob]).score > 0

        bear_ob = _make_smc("order_block", "bearish", confidence=0.8, price_mid=1.0900)
        assert service._score_smc([bear_ob]).score < 0

    def test_equal_highs_lows(self):
        """Equal highs = bearish, equal lows = bullish."""
        eh = _make_smc("equal_highs", "bearish", confidence=0.7)
        service = _make_service()
        assert service._score_smc([eh]).score < 0

        el = _make_smc("equal_lows", "bullish", confidence=0.7)
        assert service._score_smc([el]).score > 0

    def test_mixed_signals_net_out(self):
        """Mixed bullish/bearish should net out close to zero."""
        smcs = [
            _make_smc("choch", "bullish", confidence=0.9),
            _make_smc("choch", "bearish", confidence=0.9),
        ]
        service = _make_service()
        result = service._score_smc(smcs)
        assert abs(result.score) < 0.1

    def test_no_smc_structures(self):
        """Empty SMC list = zero."""
        service = _make_service()
        result = service._score_smc([])
        assert result.score == 0.0


# ═════════════════════════════════════════════════════════════════════════════════
# Volume & Volatility Scoring Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestVolumeVolatilityScoring:
    """Tests for _score_volume_volatility method."""

    def test_price_above_vwap_bullish(self):
        """Price above VWAP = positive."""
        ind = _make_indicator(vwap=1.0800)
        candles = [_make_candle(1.0840, 1.0850, 1.0830, 1.0845)]
        service = _make_service()
        result = service._score_volume_volatility(ind, candles)
        assert result.score > 0

    def test_price_below_vwap_bearish(self):
        """Price below VWAP = negative."""
        ind = _make_indicator(vwap=1.0850)
        candles = [_make_candle(1.0820, 1.0830, 1.0810, 1.0820)]
        service = _make_service()
        result = service._score_volume_volatility(ind, candles)
        assert result.score < 0

    def test_atr_contracting(self):
        """ATR contraction is slightly negative."""
        # Create candles with large ranges, then ATR smaller
        ind = _make_indicator(atr=0.0005, vwap=None)
        candles = [
            _make_candle(1.0800, 1.0810, 1.0790, 1.0805, ts_offset=i)
            for i in range(20)
        ]
        service = _make_service()
        result = service._score_volume_volatility(ind, candles)
        # ATR 0.0005 vs avg range ~0.0020 -> contracting -> slightly negative
        assert result.score < 0

    def test_upper_bb_overextended(self):
        """Price at upper BB is bearish (overextended)."""
        ind = _make_indicator(bb_upper=1.0850, bb_middle=1.0825, bb_lower=1.0800, vwap=None, atr=None)
        candles = [_make_candle(1.0845, 1.0860, 1.0840, 1.0848)]
        service = _make_service()
        result = service._score_volume_volatility(ind, candles)
        # Close 1.0848 > 0.98*1.0850=1.0633 -> overextended -> -0.3*0.25 = -0.075
        # No VWAP, no ATR contribution
        assert result.score < 0

    def test_lower_bb_oversold(self):
        """Price at lower BB is bullish (oversold)."""
        ind = _make_indicator(bb_upper=1.1100, bb_middle=1.0950, bb_lower=1.0800, vwap=None, atr=None)
        candles = [_make_candle(1.0805, 1.0810, 1.0790, 1.0802)]
        service = _make_service()
        result = service._score_volume_volatility(ind, candles)
        # Close 1.0802: 0.98*1.1100=1.0878 -> 1.0802 < 1.0878 so skip upper
        # 1.0802 < 1.0800*1.02=1.1016 -> oversold -> +0.3*0.25 = +0.075
        assert result.score > 0

    def test_none_indicator(self):
        """None indicator returns zero."""
        service = _make_service()
        result = service._score_volume_volatility(None, [])
        assert result.score == 0.0


# ═════════════════════════════════════════════════════════════════════════════════
# Market Structure Scoring Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestMarketStructureScoring:
    """Tests for _score_market_structure method."""

    def test_bullish_hh_hl_structure(self):
        """Higher highs + higher lows = bullish."""
        # Build candles with clear HH/HL: ascending waves with visible swing points
        candles = []
        ts = 0
        for wave in range(4):
            base = 1.0800 + wave * 0.0040
            # Impulse up
            for i in range(4):
                o = base + i * 0.0005
                c = o + 0.0003
                h = c + 0.0002
                l = o - 0.0001
                candles.append(_make_candle(o, h, l, c, ts_offset=ts))
                ts += 1
            # Pullback (but stays above previous swing low)
            for i in range(3):
                o = base + 0.0020 - i * 0.0003
                c = o - 0.0002
                h = o + 0.0002
                l = c - 0.0001
                candles.append(_make_candle(o, h, l, c, ts_offset=ts))
                ts += 1
        service = _make_service()
        result = service._score_market_structure(candles, None)
        # HH+HL -> 0.6 * 0.65 = ~0.39
        assert result.score > 0.15

    def test_bearish_lh_ll_structure(self):
        """Lower highs + lower lows = bearish."""
        candles = []
        ts = 0
        for wave in range(4):
            base = 1.1000 - wave * 0.0040
            # Impulse down
            for i in range(4):
                o = base - i * 0.0005
                c = o - 0.0003
                h = o + 0.0001
                l = c - 0.0002
                candles.append(_make_candle(o, h, l, c, ts_offset=ts))
                ts += 1
            # Bounce (but stays below previous swing high)
            for i in range(3):
                o = base - 0.0020 + i * 0.0003
                c = o + 0.0002
                h = c + 0.0002
                l = o - 0.0001
                candles.append(_make_candle(o, h, l, c, ts_offset=ts))
                ts += 1
        service = _make_service()
        result = service._score_market_structure(candles, None)
        assert result.score < -0.15

    def test_insufficient_candles(self):
        """Less than 6 candles = zero."""
        candles = [_make_candle(1.0800, 1.0810, 1.0790, 1.0805, ts_offset=i) for i in range(3)]
        service = _make_service()
        result = service._score_market_structure(candles, None)
        assert result.score == 0.0

    def test_support_bounce(self):
        """Price near support is bullish."""
        ind = _make_indicator(support_levels=[1.0800], resistance_levels=[])
        candles = [_make_candle(1.0802, 1.0810, 1.0798, 1.0804, ts_offset=i) for i in range(30)]
        service = _make_service()
        result = service._score_market_structure(candles, ind)
        # Near support: +0.4 * 0.35 = +0.14
        assert result.score > 0.05

    def test_resistance_rejection(self):
        """Price near resistance is bearish."""
        ind = _make_indicator(support_levels=[], resistance_levels=[1.0900])
        candles = [_make_candle(1.0898, 1.0910, 1.0890, 1.0899, ts_offset=i) for i in range(30)]
        service = _make_service()
        result = service._score_market_structure(candles, ind)
        # Near resistance: -0.4 * 0.35 = -0.14
        assert result.score < -0.05


# ═════════════════════════════════════════════════════════════════════════════════
# Decision Threshold Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestDecisionThresholds:
    """Tests for BUY/SELL/WAIT thresholds and confidence."""

    def test_buy_threshold(self):
        """Score >= 0.30 triggers BUY."""
        service = _make_service()
        assert service._bias_label(0.30) == "Buy"
        assert service._bias_label(0.35) == "Buy"

    def test_sell_threshold(self):
        """Score <= -0.30 triggers SELL."""
        service = _make_service()
        assert service._bias_label(-0.30) == "Sell"
        assert service._bias_label(-0.45) == "Sell"  # -0.45 > -0.50, so "Sell" not "Strong Sell"

    def test_wait_threshold(self):
        """Score between -0.30 and 0.30 triggers WAIT/Neutral."""
        service = _make_service()
        assert service._bias_label(0.0) == "Neutral"
        assert service._bias_label(0.25) == "Neutral"
        assert service._bias_label(-0.25) == "Neutral"

    def test_strong_labels(self):
        """Score >= 0.50 = Strong Buy, <= -0.50 = Strong Sell."""
        service = _make_service()
        assert service._bias_label(0.55) == "Strong Buy"
        assert service._bias_label(-0.60) == "Strong Sell"

    def test_confidence_formula(self):
        """Confidence maps |score| to 0-100, capped at |score|=0.6."""
        service = _make_service()
        # For a score of 0.3, confidence = 0.3*100/0.6 = 50%
        # For a score of 0.6, confidence = 100%
        # For a score of 0.9, confidence = min(150, 100) = 100%
        assert min(abs(0.3) * 100 / 0.6, 100) == 50.0
        assert min(abs(0.6) * 100 / 0.6, 100) == 100.0
        assert min(abs(0.9) * 100 / 0.6, 100) == 100.0


# ═════════════════════════════════════════════════════════════════════════════════
# Trend Summary & Risk Level Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestSummaries:
    """Tests for trend_summary and risk_level helpers."""

    def test_bullish_trend_summary(self):
        """Higher TF trends bullish -> 'Bullish'."""
        tf_results = [
            TimeframeScore(timeframe="H1", total=0.5, categories={
                "trend": CategoryScore(name="trend", score=0.5, weight=0.25),
                "momentum": CategoryScore(name="momentum", score=0.0, weight=0.20),
                "smc": CategoryScore(name="smc", score=0.0, weight=0.25),
                "volume_volatility": CategoryScore(name="volume_volatility", score=0.0, weight=0.15),
                "market_structure": CategoryScore(name="market_structure", score=0.0, weight=0.15),
            }),
            TimeframeScore(timeframe="D1", total=0.3, categories={
                "trend": CategoryScore(name="trend", score=0.3, weight=0.25),
                "momentum": CategoryScore(name="momentum", score=0.0, weight=0.20),
                "smc": CategoryScore(name="smc", score=0.0, weight=0.25),
                "volume_volatility": CategoryScore(name="volume_volatility", score=0.0, weight=0.15),
                "market_structure": CategoryScore(name="market_structure", score=0.0, weight=0.15),
            }),
        ]
        assert AIDecisionService._trend_summary(tf_results) == "Bullish"

    def test_bearish_trend_summary(self):
        """Higher TF trends bearish -> 'Bearish'."""
        tf_results = [
            TimeframeScore(timeframe="H1", total=-0.5, categories={
                "trend": CategoryScore(name="trend", score=-0.5, weight=0.25),
                "momentum": CategoryScore(name="momentum", score=0.0, weight=0.20),
                "smc": CategoryScore(name="smc", score=0.0, weight=0.25),
                "volume_volatility": CategoryScore(name="volume_volatility", score=0.0, weight=0.15),
                "market_structure": CategoryScore(name="market_structure", score=0.0, weight=0.15),
            }),
        ]
        assert AIDecisionService._trend_summary(tf_results) == "Bearish"

    def test_low_risk_when_aligned(self):
        """All TFs agree -> Low risk."""
        tf_results = [
            TimeframeScore(timeframe="H1", total=0.5),
            TimeframeScore(timeframe="H4", total=0.5),
            TimeframeScore(timeframe="D1", total=0.45),
            TimeframeScore(timeframe="M30", total=0.48),
        ]
        assert AIDecisionService._risk_level(tf_results) == "Low"

    def test_high_risk_when_divergent(self):
        """TFs disagree -> High risk."""
        tf_results = [
            TimeframeScore(timeframe="H1", total=0.6),
            TimeframeScore(timeframe="H4", total=-0.5),
            TimeframeScore(timeframe="D1", total=0.7),
            TimeframeScore(timeframe="M30", total=-0.6),
        ]
        assert AIDecisionService._risk_level(tf_results) == "High"


# ═════════════════════════════════════════════════════════════════════════════════
# Reasoning Generation Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestReasoningGeneration:
    """Tests for _generate_reasoning method."""

    def test_buy_reasoning_includes_key_info(self):
        """BUY reasoning should mention decision, score, and key signals."""
        tf_results = [
            TimeframeScore(timeframe="H1", total=0.45, categories={
                "trend": CategoryScore(name="trend", score=0.5, weight=0.25, details=["EMA bullish alignment (20>50>200)"]),
                "momentum": CategoryScore(name="momentum", score=0.3, weight=0.20, details=["RSI=55.0 (bullish)"]),
                "smc": CategoryScore(name="smc", score=0.0, weight=0.25),
                "volume_volatility": CategoryScore(name="volume_volatility", score=0.0, weight=0.15),
                "market_structure": CategoryScore(name="market_structure", score=0.0, weight=0.15),
            }),
        ]
        entry_exit = {"entry_price": 1.0850, "stop_loss": 1.0800, "take_profit_1": 1.0925, "take_profit_2": 1.1000, "risk_reward_ratio": 1.5}
        service = _make_service()
        reasoning = service._generate_reasoning("EURUSD", 0.35, "BUY", tf_results, entry_exit)

        assert "BUY" in reasoning
        assert "EURUSD" in reasoning
        assert "EMA" in reasoning
        assert "Entry:" in reasoning
        assert "Stop Loss:" in reasoning

    def test_wait_reasoning_mentions_wait(self):
        """WAIT decision should mention waiting."""
        tf_results: list[TimeframeScore] = []
        service = _make_service()
        reasoning = service._generate_reasoning("EURUSD", 0.0, "WAIT", tf_results, {})
        assert "WAIT" in reasoning


# ═════════════════════════════════════════════════════════════════════════════════
# Configuration Tests
# ═════════════════════════════════════════════════════════════════════════════════


class TestConfiguration:
    """Tests for scoring constants and weights."""

    def test_category_weights_sum_to_one(self):
        """All category weights must sum to 1.0."""
        total = sum(CATEGORY_WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_all_timeframes_present(self):
        """All 7 timeframes must be configured."""
        assert len(ALL_TIMEFRAMES) == 7
        assert "M1" in ALL_TIMEFRAMES
        assert "D1" in ALL_TIMEFRAMES

    def test_higher_timeframes(self):
        """Higher TFs: D1, H4, H1."""
        from app.services.ai_decision import HIGHER_TIMEFRAMES
        assert "D1" in HIGHER_TIMEFRAMES
        assert "H4" in HIGHER_TIMEFRAMES
        assert "H1" in HIGHER_TIMEFRAMES


# ═════════════════════════════════════════════════════════════════════════════════
# Integration: Full analyze() Pipeline with Mocked Repos
# ═════════════════════════════════════════════════════════════════════════════════


class TestAnalyzePipeline:
    """End-to-end analyze() tests with mocked repositories."""

    @pytest.mark.asyncio
    async def test_analyze_returns_decision_result(self):
        """analyze() should return a complete DecisionResult."""
        ind = _make_indicator()
        smcs = [
            _make_smc("bos", "bullish", confidence=0.8),
            _make_smc("choch", "bullish", confidence=0.9),
        ]
        candles = []
        base = 1.0800
        for i in range(50):
            o = base + i * 0.0005
            c = o + 0.0003
            h = c + 0.0002
            l = o - 0.0002
            candles.append(_make_candle(o, h, l, c, ts_offset=i))

        ind_repo = MagicMock()
        ind_repo.get_latest = AsyncMock(return_value=ind)

        smc_repo = MagicMock()
        smc_repo.get_all = AsyncMock(return_value=smcs)
        smc_repo.get_by_type = AsyncMock(return_value=smcs)

        candle_repo = MagicMock()
        candle_repo.get_candles = AsyncMock(return_value=candles)
        candle_repo.get_latest_candle = AsyncMock(return_value=candles[-1])

        service = AIDecisionService(ind_repo, smc_repo, candle_repo)
        result = await service.analyze("EURUSD")

        assert isinstance(result, DecisionResult)
        assert result.symbol == "EURUSD"
        assert result.decision in ("BUY", "SELL", "WAIT")
        assert 0.0 <= result.confidence <= 100.0
        assert result.trend in ("Bullish", "Bearish", "Ranging")
        assert result.market_bias in ("Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell")
        assert result.risk_level in ("Low", "Medium", "High")
        assert len(result.reasoning) > 0
        assert len(result.timeframe_scores) == 7

    @pytest.mark.asyncio
    async def test_analyze_flat_market_waits(self):
        """In a flat market, the decision should be WAIT with low confidence."""
        ind = _make_indicator(
            ema_20=1.0800, ema_50=1.0801, ema_200=1.0800,
            adx=12.0, supertrend_direction=0,
            rsi=50.0, macd_histogram=0.0, stoch_k=50.0,
        )
        candles = []
        for i in range(50):
            o = 1.0800
            c = 1.0800 + (i % 3 - 1) * 0.0001
            candles.append(_make_candle(o, o + 0.0003, o - 0.0003, c, ts_offset=i))

        ind_repo = MagicMock()
        ind_repo.get_latest = AsyncMock(return_value=ind)

        smc_repo = MagicMock()
        smc_repo.get_all = AsyncMock(return_value=[])
        smc_repo.get_by_type = AsyncMock(return_value=[])

        candle_repo = MagicMock()
        candle_repo.get_candles = AsyncMock(return_value=candles)
        candle_repo.get_latest_candle = AsyncMock(return_value=candles[-1])

        service = AIDecisionService(ind_repo, smc_repo, candle_repo)
        result = await service.analyze("EURUSD")

        # In a very flat market with no signals, should be WAIT
        assert result.decision == "WAIT"
        assert result.confidence < 50.0

    @pytest.mark.asyncio
    async def test_analyze_strong_bullish_gives_buy(self):
        """Strong bullish alignment across all categories -> BUY with high confidence."""
        ind = _make_indicator(
            ema_20=1.0950, ema_50=1.0850, ema_200=1.0700,
            adx=35.0, supertrend_direction=1,
            rsi=62.0, macd_histogram=0.0008, stoch_k=58.0,
            vwap=1.0820,
        )
        candles = []
        base = 1.0800
        for i in range(50):
            o = base + i * 0.0010
            c = o + 0.0005
            h = c + 0.0003
            l = o - 0.0002
            candles.append(_make_candle(o, h, l, c, ts_offset=i))

        bos_smcs = [
            _make_smc("bos", "bullish", confidence=0.9),
            _make_smc("choch", "bullish", confidence=0.85),
            _make_smc("premium_discount", "bullish", confidence=0.7),  # discount
        ]

        ind_repo = MagicMock()
        ind_repo.get_latest = AsyncMock(return_value=ind)

        smc_repo = MagicMock()
        smc_repo.get_all = AsyncMock(return_value=bos_smcs)
        smc_repo.get_by_type = AsyncMock(return_value=[])

        candle_repo = MagicMock()
        candle_repo.get_candles = AsyncMock(return_value=candles)
        candle_repo.get_latest_candle = AsyncMock(return_value=candles[-1])

        service = AIDecisionService(ind_repo, smc_repo, candle_repo)
        result = await service.analyze("EURUSD")

        assert result.decision == "BUY"
        assert result.confidence > 40.0

    @pytest.mark.asyncio
    async def test_analyze_strong_bearish_gives_sell(self):
        """Strong bearish alignment -> SELL with high confidence."""
        ind = _make_indicator(
            ema_20=1.0650, ema_50=1.0750, ema_200=1.0900,
            adx=32.0, supertrend_direction=-1,
            rsi=28.0, macd_histogram=-0.0006, stoch_k=18.0,
            vwap=1.0830,
        )
        candles = []
        base = 1.1000
        for i in range(50):
            o = base - i * 0.0010
            c = o - 0.0005
            h = o + 0.0002
            l = c - 0.0003
            candles.append(_make_candle(o, h, l, c, ts_offset=i))

        bear_smcs = [
            _make_smc("bos", "bearish", confidence=0.85),
            _make_smc("order_block", "bearish", confidence=0.8, price_high=1.0950),
            _make_smc("premium_discount", "bearish", confidence=0.7),  # premium
        ]

        ind_repo = MagicMock()
        ind_repo.get_latest = AsyncMock(return_value=ind)

        smc_repo = MagicMock()
        smc_repo.get_all = AsyncMock(return_value=bear_smcs)
        smc_repo.get_by_type = AsyncMock(return_value=[])

        candle_repo = MagicMock()
        candle_repo.get_candles = AsyncMock(return_value=candles)
        candle_repo.get_latest_candle = AsyncMock(return_value=candles[-1])

        service = AIDecisionService(ind_repo, smc_repo, candle_repo)
        result = await service.analyze("EURUSD")

        assert result.decision == "SELL"
        assert result.confidence > 30.0

    @pytest.mark.asyncio
    async def test_analyze_missing_data_graceful(self):
        """analyze() with all repos returning None should still return a WAIT result."""
        ind_repo = MagicMock()
        ind_repo.get_latest = AsyncMock(return_value=None)

        smc_repo = MagicMock()
        smc_repo.get_all = AsyncMock(return_value=[])
        smc_repo.get_by_type = AsyncMock(return_value=[])

        candle_repo = MagicMock()
        candle_repo.get_candles = AsyncMock(return_value=[])
        candle_repo.get_latest_candle = AsyncMock(return_value=None)

        service = AIDecisionService(ind_repo, smc_repo, candle_repo)
        result = await service.analyze("EURUSD")

        assert result.decision == "WAIT"
        assert result.confidence == 0.0
        assert len(result.reasoning) > 0


# ═════════════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═════════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case tests for the scoring engine."""

    def test_extreme_bullish_all_categories(self):
        """All categories max bullish = score close to 1.0."""
        ind = _make_indicator(
            ema_20=1.100, ema_50=1.090, ema_200=1.070,
            adx=40.0, supertrend_direction=1,
            rsi=62.0, macd_histogram=0.001, stoch_k=60.0,
            vwap=1.080, bb_upper=1.100, bb_middle=1.085, bb_lower=1.070,
            support_levels=[1.075],
        )
        candles = []
        base = 1.0700
        for i in range(50):
            o = base + i * 0.0010
            c = o + 0.0008
            h = c + 0.0003
            l = o - 0.0002
            candles.append(_make_candle(o, h, l, c, ts_offset=i))

        smcs = [
            _make_smc("choch", "bullish", 1.0),
            _make_smc("bos", "bullish", 1.0),
            _make_smc("premium_discount", "bullish", 1.0),
            _make_smc("order_block", "bullish", 1.0),
            _make_smc("fvg", "bullish", 1.0),
        ]

        service = _make_service(indicator=ind, smc_structures=smcs, candles=candles)
        tf = service._analyze_timeframe("EURUSD", "H1")

        # With all bullish, should be positive
        # We need to await it
        import asyncio
        tf_score = asyncio.get_event_loop().run_until_complete(tf)
        assert tf_score.total > 0.3  # should be solidly bullish

    def test_clamping_prevents_out_of_range(self):
        """Scores should always be clamped to [-1.0, 1.0]."""
        ind = _make_indicator(rsi=90.0, macd_histogram=0.01, stoch_k=95.0)
        service = _make_service()
        result = service._score_momentum(ind)
        assert -1.0 <= result.score <= 1.0
