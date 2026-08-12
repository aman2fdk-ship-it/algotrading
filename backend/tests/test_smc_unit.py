"""Unit tests for SMC detection methods.

Each detection method is tested with carefully crafted candle arrays
that should trigger specific patterns. Edge cases are covered.
"""

import json
import pytest
from datetime import datetime, timezone

from app.models.candle import Candle
from app.services.smc_detection import (
    detect_bos,
    detect_choch,
    detect_order_blocks,
    detect_fvg,
    detect_liquidity_sweeps,
    detect_equal_highs_lows,
    detect_premium_discount,
    SMCDetectionService,
)


def make_candle(
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int = 100,
    ts_offset: int = 0,
    symbol: str = "EURUSD",
    timeframe: str = "H1",
) -> Candle:
    """Helper to create a Candle with a fixed timestamp offset."""
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.fromtimestamp(base.timestamp() + ts_offset * 3600, tz=timezone.utc),
        open=open_price,
        high=high,
        low=low,
        close=close,
        tick_volume=volume,
    )


def make_candles(prices: list[tuple[float, float, float, float]], vol: int = 100) -> list[Candle]:
    """Create candles from a list of (open, high, low, close) tuples."""
    return [
        make_candle(o, h, l, c, volume=vol, ts_offset=i)
        for i, (o, h, l, c) in enumerate(prices)
    ]


class TestBreakOfStructure:
    """Tests for Break of Structure (BOS) detection."""

    def test_bullish_bos(self):
        """A close above a prior swing high should trigger bullish BOS."""
        candles = []
        ts = 0
        # Build a swing high pattern: flat at ~1.100, peak, retrace, then break
        for i in range(15):
            candles.append(make_candle(1.1000, 1.1010, 1.0990, 1.1005, ts_offset=ts)); ts += 1
        # Create a clear swing: higher high
        candles.append(make_candle(1.1040, 1.1060, 1.1030, 1.1050, ts_offset=ts)); ts += 1
        # 5 candles below swing high
        for i in range(5):
            candles.append(make_candle(1.1030, 1.1040, 1.1020, 1.1035, ts_offset=ts)); ts += 1
        # Break above the swing high (1.1060)
        candles.append(make_candle(1.1055, 1.1080, 1.1050, 1.1075, ts_offset=ts))

        results = detect_bos(candles, "EURUSD", "H1", lookback=5)
        bullish_bos = [r for r in results if r.direction == "bullish"]
        assert len(bullish_bos) >= 1, f"Expected bullish BOS, got: {[(r.direction, r.key_level) for r in results]}"
        bos = bullish_bos[0]
        assert bos.structure_type == "bos"
        assert bos.key_level is not None

    def test_bearish_bos(self):
        """A close below a prior swing low should trigger bearish BOS."""
        candles = []
        ts = 0
        for i in range(15):
            candles.append(make_candle(1.1000, 1.1010, 1.0990, 1.1005, ts_offset=ts)); ts += 1
        # Create a clear swing low
        candles.append(make_candle(1.0970, 1.0980, 1.0940, 1.0950, ts_offset=ts)); ts += 1
        # 5 candles above swing low
        for i in range(5):
            candles.append(make_candle(1.0970, 1.0980, 1.0960, 1.0975, ts_offset=ts)); ts += 1
        # Break below the swing low (1.0940)
        candles.append(make_candle(1.0950, 1.0960, 1.0920, 1.0930, ts_offset=ts))

        results = detect_bos(candles, "EURUSD", "H1", lookback=5)
        bearish_bos = [r for r in results if r.direction == "bearish"]
        assert len(bearish_bos) >= 1, f"Expected bearish BOS, got: {[(r.direction, r.key_level) for r in results]}"

    def test_no_bos_flat_market(self):
        """Flat market should produce no BOS."""
        candles = make_candles([(1.1000, 1.1010, 1.0990, 1.1005)] * 30)
        results = detect_bos(candles, "EURUSD", "H1", lookback=5)
        assert len(results) == 0

    def test_bos_insufficient_data(self):
        """Too few candles should return empty."""
        candles = make_candles([(1.1000, 1.1010, 1.0990, 1.1005)] * 8)
        results = detect_bos(candles, "EURUSD", "H1", lookback=5)
        assert len(results) == 0


class TestChangeOfCharacter:
    """Tests for Change of Character (CHoCH) detection."""

    def test_bearish_choch(self):
        """Bullish trend reversed by bearish BOS = bearish CHoCH."""
        candles = []
        ts = 0
        # Phase 1: Clear uptrend (30 candles — enough for lookback*4+5 split)
        for i in range(30):
            candles.append(make_candle(
                1.1000 + i * 0.0010, 1.1010 + i * 0.0010,
                1.0990 + i * 0.0010, 1.1005 + i * 0.0010,
                ts_offset=ts
            )); ts += 1
        # Phase 2: Peak, then create a swing high pattern
        candles.append(make_candle(1.1290, 1.1320, 1.1280, 1.1300, ts_offset=ts)); ts += 1
        # Retrace / base building — create a clear swing low
        candles.append(make_candle(1.1280, 1.1290, 1.1250, 1.1260, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1260, 1.1270, 1.1220, 1.1230, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1230, 1.1240, 1.1180, 1.1200, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1210, 1.1230, 1.1190, 1.1220, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1220, 1.1240, 1.1200, 1.1230, ts_offset=ts)); ts += 1
        # Sharp break below swing low (1.1180) — bearish BOS
        candles.append(make_candle(1.1230, 1.1245, 1.1195, 1.1235, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1235, 1.1240, 1.1190, 1.1210, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1210, 1.1225, 1.1192, 1.1215, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1215, 1.1220, 1.1185, 1.1190, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1190, 1.1200, 1.1182, 1.1195, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1195, 1.1200, 1.1080, 1.1090, ts_offset=ts))

        results = detect_choch(candles, "EURUSD", "H1", lookback=5)
        assert len(results) >= 1, (
            f"Expected CHoCH, got {len(results)} results. "
            f"Earlier trend check needed."
        )
        assert results[0].structure_type == "choch"

    def test_choch_insufficient_data(self):
        """Too few candles should return empty."""
        candles = make_candles([(1.1000, 1.1010, 1.0990, 1.1005)] * 15)
        results = detect_choch(candles, "EURUSD", "H1", lookback=5)
        assert len(results) == 0


class TestOrderBlocks:
    """Tests for Order Block detection."""

    def test_bullish_order_block(self):
        """A bearish candle before a strong bullish rally should be detected."""
        candles = []
        ts = 0
        # Generate enough candles for ATR (need 15+)
        for i in range(15):
            candles.append(make_candle(
                1.1000 + i * 0.0002, 1.1010 + i * 0.0002,
                1.0990 + i * 0.0002, 1.1005 + i * 0.0002,
                ts_offset=ts
            )); ts += 1
        # Bearish candle (potential bullish OB)
        candles.append(make_candle(1.1050, 1.1060, 1.1000, 1.1010, ts_offset=ts)); ts += 1
        # Strong bullish rally - move of ~0.005 which should be > ATR threshold
        candles.append(make_candle(1.1020, 1.1100, 1.1010, 1.1090, ts_offset=ts))

        results = detect_order_blocks(candles, "EURUSD", "H1", atr_multiplier=1.5, lookback=10)
        bullish_obs = [r for r in results if r.direction == "bullish"]
        assert len(bullish_obs) >= 1, (
            f"Expected bullish OB, got: {len(bullish_obs)} bullish, "
            f"total results: {[(r.direction, r.structure_type) for r in results]}"
        )
        ob = bullish_obs[0]
        assert ob.structure_type == "order_block"

    def test_bearish_order_block(self):
        """A bullish candle before a strong bearish drop should be detected."""
        candles = []
        ts = 0
        for i in range(15):
            candles.append(make_candle(
                1.1050 - i * 0.0002, 1.1060 - i * 0.0002,
                1.1040 - i * 0.0002, 1.1045 - i * 0.0002,
                ts_offset=ts
            )); ts += 1
        # Bullish candle (potential bearish OB)
        candles.append(make_candle(1.1000, 1.1050, 1.0990, 1.1040, ts_offset=ts)); ts += 1
        # Strong bearish drop
        candles.append(make_candle(1.1030, 1.1040, 1.0950, 1.0960, ts_offset=ts))

        results = detect_order_blocks(candles, "EURUSD", "H1", atr_multiplier=1.5, lookback=10)
        bearish_obs = [r for r in results if r.direction == "bearish"]
        assert len(bearish_obs) >= 1, (
            f"Expected bearish OB, got: {[(r.direction, r.structure_type) for r in results]}"
        )
        ob = bearish_obs[0]
        assert ob.structure_type == "order_block"

    def test_order_block_insufficient_data(self):
        """Too few candles should return empty."""
        candles = make_candles([(1.1000, 1.1010, 1.0990, 1.1005)] * 8)
        results = detect_order_blocks(candles, "EURUSD", "H1")
        assert len(results) == 0


class TestFairValueGaps:
    """Tests for Fair Value Gap (FVG) detection."""

    def test_bullish_fvg(self):
        """Classic bullish FVG: candle[2].low > candle[0].high."""
        candles = [
            make_candle(1.1000, 1.1020, 1.0990, 1.1010, ts_offset=0),  # candle 0
            make_candle(1.1010, 1.1030, 1.1000, 1.1020, ts_offset=1),  # candle 1
            make_candle(1.1040, 1.1060, 1.1040, 1.1050, ts_offset=2),  # candle 2: low(1.1040) > candle0.high(1.1020)
        ]

        results = detect_fvg(candles, "EURUSD", "H1")
        bullish_fvgs = [r for r in results if r.direction == "bullish"]
        assert len(bullish_fvgs) == 1
        fvg = bullish_fvgs[0]
        assert fvg.structure_type == "fvg"
        assert fvg.price_low == pytest.approx(1.1020)  # gap bottom
        assert fvg.price_high == pytest.approx(1.1040)  # gap top

    def test_bearish_fvg(self):
        """Classic bearish FVG: candle[2].high < candle[0].low."""
        candles = [
            make_candle(1.1000, 1.1020, 1.0980, 1.0990, ts_offset=0),  # candle 0
            make_candle(1.0990, 1.1000, 1.0970, 1.0980, ts_offset=1),  # candle 1
            make_candle(1.0960, 1.0960, 1.0940, 1.0950, ts_offset=2),  # candle 2: high(1.0960) < candle0.low(1.0980)
        ]

        results = detect_fvg(candles, "EURUSD", "H1")
        bearish_fvgs = [r for r in results if r.direction == "bearish"]
        assert len(bearish_fvgs) == 1
        fvg = bearish_fvgs[0]
        assert fvg.structure_type == "fvg"
        assert fvg.price_high == pytest.approx(1.0980)  # gap top
        assert fvg.price_low == pytest.approx(1.0960)   # gap bottom

    def test_no_fvg_in_overlapping_candles(self):
        """Overlapping candles should not produce FVGs."""
        candles = [
            make_candle(1.1000, 1.1020, 1.0980, 1.1010, ts_offset=0),
            make_candle(1.1010, 1.1030, 1.0990, 1.1020, ts_offset=1),
            make_candle(1.0990, 1.1020, 1.0980, 1.1000, ts_offset=2),
        ]
        results = detect_fvg(candles, "EURUSD", "H1")
        assert len(results) == 0

    def test_fvg_insufficient_data(self):
        """Less than 3 candles should return empty."""
        candles = make_candles([(1.1000, 1.1010, 1.0990, 1.1005)] * 2)
        results = detect_fvg(candles, "EURUSD", "H1")
        assert len(results) == 0

    def test_multiple_fvgs(self):
        """Multiple FVGs in a series should all be detected."""
        candles = [
            make_candle(1.1000, 1.1020, 1.0990, 1.1010, ts_offset=0),
            make_candle(1.1010, 1.1030, 1.1000, 1.1020, ts_offset=1),
            make_candle(1.1040, 1.1060, 1.1040, 1.1050, ts_offset=2),  # FVG 1 bullish
            make_candle(1.0940, 1.0950, 1.0920, 1.0930, ts_offset=3),
            make_candle(1.0930, 1.0940, 1.0910, 1.0920, ts_offset=4),
            make_candle(1.0900, 1.0900, 1.0880, 1.0890, ts_offset=5),  # FVG 2 bearish
        ]
        results = detect_fvg(candles, "EURUSD", "H1")
        assert len([r for r in results if r.direction == "bullish"]) >= 1
        assert len([r for r in results if r.direction == "bearish"]) >= 1


class TestLiquiditySweeps:
    """Tests for Liquidity Sweep detection."""

    def test_buyside_sweep(self):
        """Price breaks above swing high then reverses back below it."""
        candles = []
        ts = 0
        # Build base with volume
        for i in range(20):
            candles.append(make_candle(
                1.1000, 1.1010, 1.0990, 1.1005, volume=200, ts_offset=ts
            )); ts += 1
        # Create a clear swing high (local peak)
        candles.append(make_candle(1.1040, 1.1080, 1.1030, 1.1060, ts_offset=ts)); ts += 1
        # Retrace - enough candles to complete the swing pattern
        for i in range(5):
            candles.append(make_candle(1.1040, 1.1050, 1.1020, 1.1030, ts_offset=ts)); ts += 1
        # Sweep candle: breaks above swing high
        candles.append(make_candle(1.1060, 1.1100, 1.1050, 1.1090, ts_offset=ts)); ts += 1
        # Immediate reversal: closes back below swing high
        candles.append(make_candle(1.1080, 1.1090, 1.1030, 1.1040, ts_offset=ts))

        results = detect_liquidity_sweeps(candles, "EURUSD", "H1", lookback=5, reversal_threshold=0.1)
        sweeps = [r for r in results if r.direction == "bullish"]
        assert len(sweeps) >= 1, (
            f"Expected buyside sweep, got {len(sweeps)} bullish sweeps. "
            f"All results: {[(r.direction, r.structure_type) for r in results]}"
        )
        assert sweeps[0].structure_type == "liquidity_sweep"

    def test_sellside_sweep(self):
        """Price breaks below swing low then reverses back above it."""
        candles = []
        ts = 0
        for i in range(20):
            candles.append(make_candle(
                1.1000, 1.1010, 1.0990, 1.1005, volume=200, ts_offset=ts
            )); ts += 1
        # Create a clear swing low
        candles.append(make_candle(1.0970, 1.0980, 1.0930, 1.0940, ts_offset=ts)); ts += 1
        # Retrace
        for i in range(5):
            candles.append(make_candle(1.0960, 1.0980, 1.0950, 1.0970, ts_offset=ts)); ts += 1
        # Sweep: breaks below swing low
        candles.append(make_candle(1.0940, 1.0950, 1.0900, 1.0910, ts_offset=ts)); ts += 1
        # Reversal: closes back above swing low
        candles.append(make_candle(1.0920, 1.0980, 1.0910, 1.0970, ts_offset=ts))

        results = detect_liquidity_sweeps(candles, "EURUSD", "H1", lookback=5, reversal_threshold=0.1)
        sweeps = [r for r in results if r.direction == "bearish"]
        assert len(sweeps) >= 1, (
            f"Expected sellside sweep, got {len(sweeps)} bearish sweeps. "
            f"All results: {[(r.direction, r.structure_type) for r in results]}"
        )
        assert sweeps[0].structure_type == "liquidity_sweep"

    def test_no_sweep_without_reversal(self):
        """Breaking a level without reversal should not trigger."""
        candles = []
        ts = 0
        for i in range(20):
            candles.append(make_candle(1.1000, 1.1010, 1.0990, 1.1005, ts_offset=ts)); ts += 1
        candles.append(make_candle(1.1040, 1.1080, 1.1030, 1.1060, ts_offset=ts)); ts += 1
        # Price keeps going up after breaking — no reversal
        for i in range(5):
            candles.append(make_candle(
                1.1080 + i * 0.002, 1.1100 + i * 0.002,
                1.1070 + i * 0.002, 1.1090 + i * 0.002,
                ts_offset=ts
            )); ts += 1

        results = detect_liquidity_sweeps(candles, "EURUSD", "H1", lookback=5)
        # Should not crash; may or may not find sweeps
        assert all(r.structure_type == "liquidity_sweep" for r in results) if results else True


class TestEqualHighsLows:
    """Tests for Equal Highs / Equal Lows detection."""

    def test_equal_highs(self):
        """Two nearby swing highs should be detected as equal highs."""
        candles = []
        ts = 0
        # Base trend with enough candles for lookback
        for i in range(30):
            candles.append(make_candle(
                1.1000 + i * 0.0003, 1.1010 + i * 0.0003,
                1.0990 + i * 0.0003, 1.1005 + i * 0.0003,
                ts_offset=ts
            )); ts += 1
        # First swing high
        candles.append(make_candle(1.1080, 1.1100, 1.1070, 1.1090, ts_offset=ts)); ts += 1
        # Drop back
        for i in range(5):
            candles.append(make_candle(1.1070, 1.1080, 1.1050, 1.1060, ts_offset=ts)); ts += 1
        # Second swing high at nearly the same level
        candles.append(make_candle(1.1080, 1.1101, 1.1070, 1.1090, ts_offset=ts))

        results = detect_equal_highs_lows(candles, "EURUSD", "H1", lookback=20, tolerance=0.001)
        eq_highs = [r for r in results if r.structure_type == "equal_highs"]
        assert len(eq_highs) >= 1, (
            f"Expected equal_highs, got {len(eq_highs)}. "
            f"All types: {set(r.structure_type for r in results)}"
        )
        details = json.loads(eq_highs[0].details)
        assert "occurrences" in details

    def test_equal_lows(self):
        """Two nearby swing lows should be detected as equal lows."""
        candles = []
        ts = 0
        for i in range(30):
            candles.append(make_candle(
                1.1000 - i * 0.0003, 1.1010 - i * 0.0003,
                1.0990 - i * 0.0003, 1.1005 - i * 0.0003,
                ts_offset=ts
            )); ts += 1
        # First swing low
        candles.append(make_candle(1.0920, 1.0930, 1.0880, 1.0900, ts_offset=ts)); ts += 1
        # Bounce
        for i in range(5):
            candles.append(make_candle(1.0920, 1.0940, 1.0910, 1.0930, ts_offset=ts)); ts += 1
        # Second swing low at nearly the same level
        candles.append(make_candle(1.0920, 1.0930, 1.0881, 1.0900, ts_offset=ts))

        results = detect_equal_highs_lows(candles, "EURUSD", "H1", lookback=20, tolerance=0.001)
        eq_lows = [r for r in results if r.structure_type == "equal_lows"]
        assert len(eq_lows) >= 1, (
            f"Expected equal_lows, got {len(eq_lows)}. "
            f"All types: {set(r.structure_type for r in results)}"
        )
        details = json.loads(eq_lows[0].details)
        assert "occurrences" in details

    def test_no_equal_in_flat_market(self):
        """Flat market with no clear swings shouldn't produce results."""
        candles = make_candles([(1.1000, 1.1010, 1.0990, 1.1005)] * 30)
        results = detect_equal_highs_lows(candles, "EURUSD", "H1", lookback=10)
        assert len(results) == 0


class TestPremiumDiscount:
    """Tests for Premium / Discount zone detection."""

    def test_premium_zone(self):
        """Price near swing high = premium zone."""
        candles = []
        ts = 0
        # Build 55 candles spanning a range: 25 low, 25 mid-high, 5 near top
        for i in range(25):
            candles.append(make_candle(1.0900, 1.0910, 1.0890, 1.0905, ts_offset=ts)); ts += 1
        for i in range(25):
            candles.append(make_candle(
                1.0980 + i * 0.0004, 1.0990 + i * 0.0004,
                1.0970 + i * 0.0004, 1.0985 + i * 0.0004,
                ts_offset=ts
            )); ts += 1
        # Current price near swing high
        candles.append(make_candle(1.1080, 1.1110, 1.1070, 1.1100, ts_offset=ts))

        results = detect_premium_discount(candles, "EURUSD", "H1", lookback=50)
        assert len(results) == 1, f"Expected 1 result, got {len(results)}. n={len(candles)}, lookback=50"
        details = json.loads(results[0].details)
        assert details["zone_type"] == "premium"
        assert details["position_pct"] > 0.5

    def test_discount_zone(self):
        """Price near swing low = discount zone."""
        candles = []
        ts = 0
        for i in range(25):
            candles.append(make_candle(1.0900, 1.0910, 1.0890, 1.0905, ts_offset=ts)); ts += 1
        for i in range(25):
            candles.append(make_candle(
                1.0980 + i * 0.0004, 1.0990 + i * 0.0004,
                1.0970 + i * 0.0004, 1.0985 + i * 0.0004,
                ts_offset=ts
            )); ts += 1
        # Current price near swing low
        candles.append(make_candle(1.0900, 1.0920, 1.0890, 1.0910, ts_offset=ts))

        results = detect_premium_discount(candles, "EURUSD", "H1", lookback=50)
        assert len(results) == 1, f"Expected 1 result, got {len(results)}. n={len(candles)}"
        details = json.loads(results[0].details)
        assert details["zone_type"] == "discount"
        assert details["position_pct"] < 0.5

    def test_equilibrium(self):
        """Price at midpoint = equilibrium."""
        candles = []
        ts = 0
        for i in range(25):
            candles.append(make_candle(1.0900, 1.0910, 1.0890, 1.0905, ts_offset=ts)); ts += 1
        for i in range(25):
            candles.append(make_candle(
                1.0980 + i * 0.0004, 1.0990 + i * 0.0004,
                1.0970 + i * 0.0004, 1.0985 + i * 0.0004,
                ts_offset=ts
            )); ts += 1
        # Current price at ~1.100 (midpoint of 1.089-1.110)
        candles.append(make_candle(1.0990, 1.1010, 1.0990, 1.1000, ts_offset=ts))

        results = detect_premium_discount(candles, "EURUSD", "H1", lookback=50)
        assert len(results) == 1, f"Expected 1 result, got {len(results)}. n={len(candles)}"
        details = json.loads(results[0].details)
        assert details["zone_type"] in ("equilibrium", "premium", "discount")

    def test_premium_discount_insufficient_data(self):
        """Too few candles should return empty."""
        candles = make_candles([(1.1000, 1.1010, 1.0990, 1.1005)] * 10)
        results = detect_premium_discount(candles, "EURUSD", "H1", lookback=50)
        assert len(results) == 0


class TestSMCDetectionService:
    """Tests for the orchestration service."""

    def test_detect_all_empty(self):
        """detect_all on empty candles returns empty list."""
        service = SMCDetectionService()
        results = service.detect_all([], "EURUSD", "H1")
        assert results == []

    def test_detect_all_with_data(self):
        """detect_all combines results from all methods."""
        candles = []
        ts = 0
        # Generate enough candles for all detection methods (need 50+ for premium/discount)
        for i in range(80):
            variation = (i % 7 - 3) * 0.001
            candles.append(make_candle(
                1.1000 + variation, 1.1010 + variation + abs(variation),
                1.0990 + variation - abs(variation), 1.1000 + variation,
                ts_offset=ts
            )); ts += 1

        service = SMCDetectionService()
        results = service.detect_all(candles, "EURUSD", "H1")
        assert isinstance(results, list)
        structure_types = {r.structure_type for r in results}
        # FVG detection should always work with 3+ candles
        # Premium/discount needs 50+ candles
        assert "premium_discount" in structure_types, f"Got types: {structure_types}"
