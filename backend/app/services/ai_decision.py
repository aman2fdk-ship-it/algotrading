"""AI Decision Engine — multi-factor weighted scoring system.

Combines technical indicators, SMC/ICT patterns, volume/volatility,
market structure, and multi-timeframe analysis into a single BUY/SELL/WAIT decision.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from app.models.candle import Candle
from app.models.smc_structure import SMCStructure
from app.models.technical_indicator import TechnicalIndicator
from app.models.ai_recommendation import AIRecommendation
from app.repositories.indicator_repository import IndicatorRepository
from app.repositories.smc_repository import SMCRepository
from app.repositories.candle_repository import CandleRepository
from app.repositories.ai_recommendation_repo import AIRecommendationRepository

logger = logging.getLogger(__name__)


def _opt_float(value) -> float | None:
    """Coerce an optional numeric value to float, tolerating None."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_datetime(value) -> datetime | None:
    """Coerce an optional datetime/ISO-string to datetime, tolerating None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None

# ── Configuration Constants ─────────────────────────────────────────────────────

ALL_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
HIGHER_TIMEFRAMES = {"D1", "H4", "H1"}
LOWER_TIMEFRAMES = {"M30", "M15", "M5", "M1"}
TIMEFRAME_WEIGHTS = {tf: 2.0 if tf in HIGHER_TIMEFRAMES else 1.0 for tf in ALL_TIMEFRAMES}

# Category weights (must sum to 1.0)
CATEGORY_WEIGHTS = {
    "trend": 0.25,
    "momentum": 0.20,
    "smc": 0.25,
    "volume_volatility": 0.15,
    "market_structure": 0.15,
}

# Decision thresholds
BUY_THRESHOLD = 0.30
SELL_THRESHOLD = -0.30

# Recent candle lookback for structure analysis
STRUCTURE_LOOKBACK = 50
SMC_LOOKBACK = 30


@dataclass
class CategoryScore:
    """Score breakdown for one signal category."""

    name: str
    score: float  # -1.0 to +1.0
    weight: float
    weighted: float = 0.0
    details: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.weighted = self.score * self.weight


@dataclass
class TimeframeScore:
    """Aggregated score for one timeframe."""

    timeframe: str
    total: float = 0.0
    categories: dict[str, CategoryScore] = field(default_factory=dict)
    weight: float = 1.0

    @property
    def weighted_total(self) -> float:
        return self.total * self.weight


@dataclass
class DecisionResult:
    """Output of the AI decision engine."""

    symbol: str
    decision: str  # BUY, SELL, WAIT
    confidence: float  # 0–100
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    risk_reward_ratio: float | None = None
    trend: str = "Ranging"
    market_bias: str = "Neutral"
    risk_level: str = "Medium"
    reasoning: str = ""
    timeframe_scores: dict[str, float] = field(default_factory=dict)
    timeframe_details: list[dict] = field(default_factory=list)
    created_at: datetime | None = None


# ═════════════════════════════════════════════════════════════════════════════════
# AIDecisionService
# ═════════════════════════════════════════════════════════════════════════════════


class AIDecisionService:
    """Multi-factor AI decision engine for forex analysis.

    Aggregates signals from indicators, SMC patterns, volume/volatility,
    and market structure across all timeframes into a single trading decision.

    Public API:
        analyze(symbol: str) -> DecisionResult
    """

    def __init__(
        self,
        indicator_repo: IndicatorRepository,
        smc_repo: SMCRepository,
        candle_repo: CandleRepository,
        recommendation_repo: AIRecommendationRepository | None = None,
        cache: "RedisCache | None" = None,
        cache_ttl: int | None = None,
    ) -> None:
        self._indicator_repo = indicator_repo
        self._smc_repo = smc_repo
        self._candle_repo = candle_repo
        self._recommendation_repo = recommendation_repo
        self._cache = cache
        self._cache_ttl = cache_ttl

    # ── Public API ──────────────────────────────────────────────────────────

    @staticmethod
    def _cache_key(symbol: str) -> str:
        return f"ai:decision:{symbol.upper()}"

    async def analyze(self, symbol: str) -> DecisionResult:
        """Return a trading decision, using a short-TTL cache when available.

        The analysis is expensive (scans every timeframe and runs many DB
        queries), so repeated requests for the same symbol within the TTL reuse
        the cached result.  If Redis is down/disabled the cache degrades to a
        miss and we compute fresh — a Redis outage never blocks or errors.
        """
        symbol = symbol.upper()
        cache_key = self._cache_key(symbol)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            logger.info("AI decision cache HIT for %s", symbol)
            return cached

        result = await self._run_analysis(symbol)
        await self._cache_set(cache_key, result)
        return result

    async def _cache_get(self, key: str) -> DecisionResult | None:
        if self._cache is None:
            return None
        try:
            data = await self._cache.get_json(key)
        except Exception:  # graceful fallback — never crash the request
            return None
        if not isinstance(data, dict):
            return None
        try:
            return DecisionResult(
                symbol=data["symbol"],
                decision=data["decision"],
                confidence=float(data["confidence"]),
                entry_price=_opt_float(data.get("entry_price")),
                stop_loss=_opt_float(data.get("stop_loss")),
                take_profit_1=_opt_float(data.get("take_profit_1")),
                take_profit_2=_opt_float(data.get("take_profit_2")),
                risk_reward_ratio=_opt_float(data.get("risk_reward_ratio")),
                trend=data.get("trend", "Ranging"),
                market_bias=data.get("market_bias", "Neutral"),
                risk_level=data.get("risk_level", "Medium"),
                reasoning=data.get("reasoning", ""),
                timeframe_scores={
                    str(k): float(v) for k, v in (data.get("timeframe_scores") or {}).items()
                },
                timeframe_details=data.get("timeframe_details") or [],
                created_at=_opt_datetime(data.get("created_at")),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("AI decision cache value malformed for %s; recomputing.", key)
            return None

    async def _cache_set(self, key: str, result: DecisionResult) -> None:
        if self._cache is None:
            return
        payload = {
            "symbol": result.symbol,
            "decision": result.decision,
            "confidence": result.confidence,
            "entry_price": result.entry_price,
            "stop_loss": result.stop_loss,
            "take_profit_1": result.take_profit_1,
            "take_profit_2": result.take_profit_2,
            "risk_reward_ratio": result.risk_reward_ratio,
            "trend": result.trend,
            "market_bias": result.market_bias,
            "risk_level": result.risk_level,
            "reasoning": result.reasoning,
            "timeframe_scores": result.timeframe_scores,
            "timeframe_details": result.timeframe_details,
            "created_at": result.created_at.isoformat() if result.created_at else None,
        }
        try:
            await self._cache.set_json(key, payload, ttl=self._cache_ttl)
        except Exception:  # graceful fallback — never crash the request
            logger.warning("AI decision cache write failed for %s; skipping.", key)

    async def _run_analysis(self, symbol: str) -> DecisionResult:
        """Run full multi-timeframe analysis and return a trading decision."""
        tf_results: list[TimeframeScore] = []

        for tf in ALL_TIMEFRAMES:
            tf_score = await self._analyze_timeframe(symbol, tf)
            tf_score.weight = TIMEFRAME_WEIGHTS[tf]
            tf_results.append(tf_score)

        # Compute overall weighted score
        total_weight = sum(TIMEFRAME_WEIGHTS[tf] for tf in ALL_TIMEFRAMES)
        overall = (
            sum(ts.total * ts.weight for ts in tf_results) / total_weight
            if total_weight > 0
            else 0.0
        )

        # Decision
        if overall >= BUY_THRESHOLD:
            decision = "BUY"
        elif overall <= SELL_THRESHOLD:
            decision = "SELL"
        else:
            decision = "WAIT"

        # Confidence: map |score| -> 0-100, capped at |score| = 0.6 = 100%
        confidence = min(abs(overall) * 100.0 / 0.6, 100.0)

        # Market bias label
        market_bias = self._bias_label(overall)

        # Trend summary
        trend = self._trend_summary(tf_results)

        # Risk level
        risk_level = self._risk_level(tf_results)

        # Entry / SL / TP
        entry_exit = await self._calculate_entry_exit(symbol, overall, tf_results)

        # Reasoning
        reasoning = self._generate_reasoning(symbol, overall, decision, tf_results, entry_exit)

        # Timeframe scores dict
        tf_scores = {ts.timeframe: round(ts.total, 4) for ts in tf_results}

        # Details for API
        tf_details = []
        for ts in tf_results:
            cat_scores = {k: round(v.score, 4) for k, v in ts.categories.items()}
            tf_details.append({
                "timeframe": ts.timeframe,
                "score": round(ts.total, 4),
                "weight": ts.weight,
                "category_scores": cat_scores,
            })

        result = DecisionResult(
            symbol=symbol,
            decision=decision,
            confidence=round(confidence, 2),
            entry_price=entry_exit.get("entry_price"),
            stop_loss=entry_exit.get("stop_loss"),
            take_profit_1=entry_exit.get("take_profit_1"),
            take_profit_2=entry_exit.get("take_profit_2"),
            risk_reward_ratio=entry_exit.get("risk_reward_ratio"),
            trend=trend,
            market_bias=market_bias,
            risk_level=risk_level,
            reasoning=reasoning,
            timeframe_scores=tf_scores,
            timeframe_details=tf_details,
            created_at=datetime.now(timezone.utc),
        )

        return result

    async def analyze_and_save(self, symbol: str) -> DecisionResult:
        """Analyze and persist the recommendation."""
        result = await self.analyze(symbol)
        if self._recommendation_repo:
            rec = AIRecommendation(
                symbol=result.symbol,
                decision=result.decision,
                confidence=result.confidence,
                entry_price=result.entry_price,
                stop_loss=result.stop_loss,
                take_profit_1=result.take_profit_1,
                take_profit_2=result.take_profit_2,
                risk_reward_ratio=result.risk_reward_ratio,
                trend=result.trend,
                market_bias=result.market_bias,
                risk_level=result.risk_level,
                reasoning=result.reasoning,
                timeframe_scores=json.dumps(result.timeframe_scores),
            )
            await self._recommendation_repo.save(rec)
            logger.info(
                "Saved AI recommendation: %s -> %s (%.1f%%)",
                symbol, result.decision, result.confidence,
            )
        return result

    # ── Per-Timeframe Analysis ──────────────────────────────────────────────

    async def _analyze_timeframe(
        self, symbol: str, timeframe: str
    ) -> TimeframeScore:
        """Score one timeframe across all signal categories."""
        indicator = await self._indicator_repo.get_latest(symbol, timeframe)
        smc_structures = await self._smc_repo.get_all(symbol, timeframe, limit=SMC_LOOKBACK)
        candles = await self._candle_repo.get_candles(
            symbol, timeframe, limit=STRUCTURE_LOOKBACK
        )

        cats: dict[str, CategoryScore] = {}

        # Trend (25%)
        cats["trend"] = self._score_trend(indicator)

        # Momentum (20%)
        cats["momentum"] = self._score_momentum(indicator)

        # SMC/ICT (25%)
        cats["smc"] = self._score_smc(smc_structures)

        # Volume & Volatility (15%)
        cats["volume_volatility"] = self._score_volume_volatility(indicator, candles)

        # Market Structure (15%)
        cats["market_structure"] = self._score_market_structure(candles, indicator)

        # Weighted total for this timeframe
        total = sum(c.score * CATEGORY_WEIGHTS[c.name] for c in cats.values())

        return TimeframeScore(
            timeframe=timeframe,
            total=total,
            categories=cats,
        )

    # ── Trend Scoring (weight: 25%) ─────────────────────────────────────────

    def _score_trend(
        self, indicator: TechnicalIndicator | None
    ) -> CategoryScore:
        """Score trend based on EMA alignment, ADX, and SuperTrend."""
        details: list[str] = []
        if indicator is None:
            return CategoryScore(name="trend", score=0.0, weight=CATEGORY_WEIGHTS["trend"])

        ema_score = 0.0
        adx_strength = 0.0
        st_score = 0.0

        # EMA alignment
        ema_vals = [indicator.ema_20, indicator.ema_50, indicator.ema_200]
        if all(v is not None for v in ema_vals):
            e20, e50, e200 = ema_vals  # type: ignore
            if e20 > e50 > e200:
                ema_score = 1.0
                details.append("EMA bullish alignment (20>50>200)")
            elif e20 < e50 < e200:
                ema_score = -1.0
                details.append("EMA bearish alignment (20<50<200)")
            else:
                ema_score = 0.0
                details.append("EMA mixed alignment")
        else:
            details.append("EMA data incomplete")

        # ADX strength modifier
        if indicator.adx is not None:
            if indicator.adx > 25:
                adx_strength = 1.0  # strong trend — no modifier needed
                details.append(f"ADX={indicator.adx:.1f} (trending)")
            elif indicator.adx >= 20:
                adx_strength = 0.5
                details.append(f"ADX={indicator.adx:.1f} (moderate)")
            else:
                adx_strength = 0.0
                details.append(f"ADX={indicator.adx:.1f} (weak/ranging)")

            # Apply ADX: if ADX < 20, trend signal is unreliable -> move toward 0
            trend_score = ema_score * adx_strength
        else:
            trend_score = ema_score

        # SuperTrend confirmation
        if indicator.supertrend_direction is not None:
            if indicator.supertrend_direction == 1:
                st_score = 1.0
                details.append("SuperTrend bullish")
            elif indicator.supertrend_direction == -1:
                st_score = -1.0
                details.append("SuperTrend bearish")
            else:
                st_score = 0.0  # neutral (direction == 0)

        # Blend: 60% EMA/ADX, 40% SuperTrend
        final = trend_score * 0.6 + st_score * 0.4

        return CategoryScore(
            name="trend",
            score=round(final, 4),
            weight=CATEGORY_WEIGHTS["trend"],
            details=details,
        )

    # ── Momentum Scoring (weight: 20%) ──────────────────────────────────────

    def _score_momentum(
        self, indicator: TechnicalIndicator | None
    ) -> CategoryScore:
        """Score momentum from RSI, MACD, and Stochastic."""
        details: list[str] = []
        if indicator is None:
            return CategoryScore(name="momentum", score=0.0, weight=CATEGORY_WEIGHTS["momentum"])

        components: list[tuple[float, str]] = []

        # RSI (weight: 0.5)
        if indicator.rsi is not None:
            rsi = indicator.rsi
            if rsi > 70:
                components.append((-0.5, f"RSI={rsi:.1f} (overbought)"))
            elif rsi > 50:
                components.append((0.5, f"RSI={rsi:.1f} (bullish)"))
            elif rsi < 30:
                components.append((0.5, f"RSI={rsi:.1f} (oversold)"))
            elif rsi < 50:
                components.append((-0.5, f"RSI={rsi:.1f} (bearish)"))
            else:
                components.append((0.0, f"RSI={rsi:.1f} (neutral)"))

        # MACD histogram (weight: 0.3)
        if indicator.macd_histogram is not None:
            hist = indicator.macd_histogram
            macd_prev = indicator.macd_line
            sig_prev = indicator.macd_signal

            if hist > 0:
                # Check if rising: positive histogram
                rising = macd_prev is not None and sig_prev is not None
                if rising:
                    components.append((0.5, f"MACD hist={hist:.5f} positive & rising"))
                else:
                    components.append((0.3, f"MACD hist={hist:.5f} positive"))
            else:
                falling = macd_prev is not None and sig_prev is not None
                if falling:
                    components.append((-0.5, f"MACD hist={hist:.5f} negative & falling"))
                else:
                    components.append((-0.3, f"MACD hist={hist:.5f} negative"))

        # Stochastic %K (weight: 0.2)
        if indicator.stoch_k is not None:
            k = indicator.stoch_k
            if k > 80:
                components.append((-0.3, f"Stoch K={k:.1f} (overbought)"))
            elif k < 20:
                components.append((0.3, f"Stoch K={k:.1f} (oversold)"))
            else:
                components.append((0.0, f"Stoch K={k:.1f} (neutral)"))

        if not components:
            return CategoryScore(name="momentum", score=0.0, weight=CATEGORY_WEIGHTS["momentum"])

        # Weighted average: RSI=0.5, MACD=0.3, Stoch=0.2
        weights = [0.5, 0.3, 0.2]
        score = sum(c[0] * w for c, w in zip(components, weights))

        for c, msg in components:
            details.append(msg)

        return CategoryScore(
            name="momentum",
            score=round(score, 4),
            weight=CATEGORY_WEIGHTS["momentum"],
            details=details,
        )

    # ── SMC/ICT Scoring (weight: 25%) ───────────────────────────────────────

    def _score_smc(
        self, smc_structures: Sequence[SMCStructure]
    ) -> CategoryScore:
        """Score based on SMC/ICT patterns present.

        Weights within SMC:
          - CHoCH: ±0.8  (strongest — trend change)
          - BOS: ±0.6
          - Order Block: ±0.5
          - FVG: ±0.4
          - Liquidity Sweep: ±0.3 (sellside=+bullish sign, buyside=+bearish sign)
          - Premium/Discount: ±0.3
        """
        details: list[str] = []
        if not smc_structures:
            details.append("No SMC patterns detected")
            return CategoryScore(name="smc", score=0.0, weight=CATEGORY_WEIGHTS["smc"])

        score_map = 0.0
        count = 0

        for s in smc_structures:
            sign = 1.0 if s.direction == "bullish" else -1.0

            if s.structure_type == "bos":
                score_map += sign * 0.6 * s.confidence
                details.append(f"BOS {s.direction} (conf={s.confidence:.2f})")
            elif s.structure_type == "choch":
                score_map += sign * 0.8 * s.confidence
                details.append(f"CHoCH {s.direction} (conf={s.confidence:.2f})")
            elif s.structure_type == "order_block":
                score_map += sign * 0.5 * s.confidence
                details.append(f"OrderBlock {s.direction} @{s.price_mid}" if s.price_mid else f"OrderBlock {s.direction}")
            elif s.structure_type == "fvg":
                score_map += sign * 0.4 * s.confidence
                details.append(f"FVG {s.direction}")
            elif s.structure_type == "liquidity_sweep":
                # Sellside sweep = liquidity taken below = bullish
                # Buyside sweep = liquidity taken above = bearish
                sweep_sign = 1.0 if s.direction == "bearish" else -1.0
                score_map += sweep_sign * 0.3 * s.confidence
                details.append(f"LiqSweep {s.direction}")
            elif s.structure_type == "premium_discount":
                score_map += sign * 0.3 * s.confidence
                details.append(
                    f"{'Discount (buy zone)' if s.direction == 'bullish' else 'Premium (sell zone)'}"
                )
            elif s.structure_type in ("equal_highs", "equal_lows"):
                # Equal highs = bearish, equal lows = bullish
                eq_sign = -1.0 if s.structure_type == "equal_highs" else 1.0
                score_map += eq_sign * 0.3 * s.confidence
                details.append(f"{s.structure_type.replace('_', ' ').title()}")

            count += 1

        # Normalize by count to avoid bias from many patterns
        raw = score_map / max(count, 1)
        clamped = max(-1.0, min(1.0, raw))

        return CategoryScore(
            name="smc",
            score=round(clamped, 4),
            weight=CATEGORY_WEIGHTS["smc"],
            details=details,
        )

    # ── Volume & Volatility Scoring (weight: 15%) ───────────────────────────

    def _score_volume_volatility(
        self,
        indicator: TechnicalIndicator | None,
        candles: Sequence[Candle],
    ) -> CategoryScore:
        """Score based on VWAP, ATR expansion, and Bollinger Bands."""
        details: list[str] = []
        components: list[float] = []

        if indicator is None:
            return CategoryScore(
                name="volume_volatility", score=0.0,
                weight=CATEGORY_WEIGHTS["volume_volatility"],
            )

        # VWAP (weight: 0.5)
        if indicator.vwap is not None and candles:
            last = candles[-1]
            if last.close > indicator.vwap:
                components.append(0.3)
                details.append(f"Price > VWAP (+{indicator.vwap - last.close:.5f})")
            else:
                components.append(-0.3)
                details.append("Price < VWAP")

        # ATR expansion (weight: 0.25)
        if indicator.atr is not None and len(candles) >= 15:
            # Compare current ATR to avg candle range
            recent_ranges = [
                abs(c.high - c.low) for c in candles[-10:]
            ]
            avg_range = sum(recent_ranges) / len(recent_ranges) if recent_ranges else 0
            if avg_range > 0 and indicator.atr > avg_range * 1.2:
                components.append(0.2)
                details.append("ATR expanding (volatility increasing)")
            elif avg_range > 0 and indicator.atr < avg_range * 0.8:
                components.append(-0.1)
                details.append("ATR contracting (volatility decreasing)")
            else:
                components.append(0.0)

        # Bollinger Bands (weight: 0.25)
        if all(v is not None for v in [indicator.bb_upper, indicator.bb_middle, indicator.bb_lower]) and candles:
            last_close = candles[-1].close
            bb_upper = indicator.bb_upper
            bb_lower = indicator.bb_lower
            bb_range = bb_upper - bb_lower if bb_upper and bb_lower else 1

            if bb_range > 0:
                if last_close > bb_upper * 0.98:
                    components.append(-0.3)
                    details.append("Price at upper BB (overextended)")
                elif last_close < bb_lower * 1.02:
                    components.append(0.3)
                    details.append("Price at lower BB (oversold)")
                else:
                    components.append(0.0)

        if not components:
            details.append("Insufficient volume/volatility data")
            return CategoryScore(
                name="volume_volatility", score=0.0,
                weight=CATEGORY_WEIGHTS["volume_volatility"],
            )

        # Weighted: VWAP=0.5, ATR=0.25, BB=0.25
        weights = [0.5, 0.25, 0.25]
        weighted = sum(c * w for c, w in zip(components, weights))
        clamped = max(-1.0, min(1.0, weighted))

        return CategoryScore(
            name="volume_volatility",
            score=round(clamped, 4),
            weight=CATEGORY_WEIGHTS["volume_volatility"],
            details=details,
        )

    # ── Market Structure Scoring (weight: 15%) ──────────────────────────────

    def _score_market_structure(
        self,
        candles: Sequence[Candle],
        indicator: TechnicalIndicator | None,
    ) -> CategoryScore:
        """Score based on price structure: HH/HL vs LH/LL, support/resistance."""
        details: list[str] = []
        if len(candles) < 6:
            details.append("Insufficient candles for structure analysis")
            return CategoryScore(
                name="market_structure", score=0.0,
                weight=CATEGORY_WEIGHTS["market_structure"],
            )

        # Identify swing highs and lows
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]

        swing_highs: list[float] = []
        swing_lows: list[float] = []

        for i in range(2, len(candles) - 2):
            if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
                swing_highs.append(highs[i])
            if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
                swing_lows.append(lows[i])

        structure_score = 0.0

        # Determine HH/HL or LH/LL
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1] > swing_highs[-2]
            hl = swing_lows[-1] > swing_lows[-2]
            lh = swing_highs[-1] < swing_highs[-2]
            ll = swing_lows[-1] < swing_lows[-2]

            if hh and hl:
                structure_score = 0.6
                details.append("HH+HL (bullish structure)")
            elif lh and ll:
                structure_score = -0.6
                details.append("LH+LL (bearish structure)")
            else:
                structure_score = 0.0
                details.append("Mixed structure (ranging)")

        # Support/resistance bounce (from indicator)
        sr_score = 0.0
        if indicator is not None and candles:
            last = candles[-1]
            # Support bounce
            if indicator.support_levels:
                nearest_support = min(
                    indicator.support_levels,
                    key=lambda s: abs(s - last.close),
                    default=None,
                )
                if nearest_support and abs(last.close - nearest_support) / last.close < 0.005:
                    sr_score += 0.4
                    details.append(f"Price near support {nearest_support}")

            # Resistance rejection
            if indicator.resistance_levels:
                nearest_resistance = min(
                    indicator.resistance_levels,
                    key=lambda r: abs(r - last.close),
                    default=None,
                )
                if nearest_resistance and abs(last.close - nearest_resistance) / last.close < 0.005:
                    sr_score -= 0.4
                    details.append(f"Price near resistance {nearest_resistance}")

        # Blend: 65% swing structure, 35% S/R
        final = structure_score * 0.65 + sr_score * 0.35
        clamped = max(-1.0, min(1.0, final))

        return CategoryScore(
            name="market_structure",
            score=round(clamped, 4),
            weight=CATEGORY_WEIGHTS["market_structure"],
            details=details,
        )

    # ── Entry / Exit Calculator ─────────────────────────────────────────────

    async def _calculate_entry_exit(
        self,
        symbol: str,
        overall_score: float,
        tf_results: list[TimeframeScore],
    ) -> dict:
        """Calculate entry price, stop loss, and take profit levels."""
        result: dict = {
            "entry_price": None,
            "stop_loss": None,
            "take_profit_1": None,
            "take_profit_2": None,
            "risk_reward_ratio": None,
        }

        # Get the latest candle on the primary timeframe (H1)
        latest_candle = await self._candle_repo.get_latest_candle(symbol, "H1")
        if latest_candle is None:
            latest_candle = await self._candle_repo.get_latest_candle(symbol, "M15")
        if latest_candle is None:
            return result

        entry_price = latest_candle.close
        result["entry_price"] = round(entry_price, 5)

        # Get ATR from H4 for SL calculation
        indicator_h4 = await self._indicator_repo.get_latest(symbol, "H4")
        indicator_h1 = await self._indicator_repo.get_latest(symbol, "H1")

        atr = None
        if indicator_h4 and indicator_h4.atr is not None:
            atr = indicator_h4.atr
        elif indicator_h1 and indicator_h1.atr is not None:
            atr = indicator_h1.atr

        # Get SMC structures for S/R-based SL
        smc_ob = await self._smc_repo.get_by_type(symbol, "H1", "order_block", limit=5)
        smc_fvg = await self._smc_repo.get_by_type(symbol, "H1", "fvg", limit=5)

        # Also check H4
        smc_ob_h4 = await self._smc_repo.get_by_type(symbol, "H4", "order_block", limit=5)

        all_smc = list(smc_ob) + list(smc_ob_h4) + list(smc_fvg)

        # Get swing levels from H1 indicator
        swing_high = None
        swing_low = None
        if indicator_h1:
            swing_high = indicator_h1.swing_high
            swing_low = indicator_h1.swing_low

        if overall_score >= BUY_THRESHOLD:
            # BUY: SL below nearest SMC structure or swing low or 2*ATR below
            sl_candidates: list[float] = []

            # Swing low
            if swing_low is not None:
                sl_candidates.append(swing_low)

            # Order block / FVG lows (bullish structures provide support)
            for s in all_smc:
                if s.direction == "bullish" and s.price_low is not None:
                    sl_candidates.append(s.price_low)
                elif s.price_low is not None:
                    sl_candidates.append(s.price_low)

            # 2× ATR fallback
            if atr is not None:
                sl_candidates.append(entry_price - 2.0 * atr)

            # Pick the highest SL below entry (tightest reasonable SL)
            sl_candidates = [s for s in sl_candidates if s < entry_price]
            if sl_candidates:
                stop_loss = max(sl_candidates)
                result["stop_loss"] = round(stop_loss, 5)

        elif overall_score <= SELL_THRESHOLD:
            # SELL: SL above nearest SMC structure or swing high or 2*ATR above
            sl_candidates: list[float] = []

            if swing_high is not None:
                sl_candidates.append(swing_high)

            for s in all_smc:
                if s.direction == "bearish" and s.price_high is not None:
                    sl_candidates.append(s.price_high)
                elif s.price_high is not None:
                    sl_candidates.append(s.price_high)

            if atr is not None:
                sl_candidates.append(entry_price + 2.0 * atr)

            # Pick the lowest SL above entry (tightest reasonable SL)
            sl_candidates = [s for s in sl_candidates if s > entry_price]
            if sl_candidates:
                stop_loss = min(sl_candidates)
                result["stop_loss"] = round(stop_loss, 5)

        # Calculate TPs
        if result["stop_loss"] is not None and result["entry_price"] is not None:
            risk_distance = abs(result["entry_price"] - result["stop_loss"])
            if overall_score >= BUY_THRESHOLD:
                result["take_profit_1"] = round(entry_price + 1.5 * risk_distance, 5)
                result["take_profit_2"] = round(entry_price + 3.0 * risk_distance, 5)
            elif overall_score <= SELL_THRESHOLD:
                result["take_profit_1"] = round(entry_price - 1.5 * risk_distance, 5)
                result["take_profit_2"] = round(entry_price - 3.0 * risk_distance, 5)

            if risk_distance > 0:
                result["risk_reward_ratio"] = round(
                    (1.5 * risk_distance) / risk_distance, 2
                )

        return result

    # ── Reasoning Generator ─────────────────────────────────────────────────

    def _generate_reasoning(
        self,
        symbol: str,
        overall: float,
        decision: str,
        tf_results: list[TimeframeScore],
        entry_exit: dict,
    ) -> str:
        """Generate a Bloomberg-style human-readable reasoning string."""
        lines: list[str] = []

        # Header
        lines.append(f"=== AI Analysis: {symbol} ===")
        lines.append(f"Decision: {decision} | Confidence: {min(abs(overall)*100/0.6, 100):.1f}%")
        lines.append(f"Score: {overall:+.4f}")
        lines.append("")

        # Multi-timeframe summary
        lines.append("--- Multi-Timeframe Scores ---")
        for ts in sorted(tf_results, key=lambda t: TIMEFRAME_WEIGHTS[t.timeframe], reverse=True):
            marker = "★" if ts.weighted_total != 0 and abs(ts.weighted_total) >= 0.2 else " "
            lines.append(
                f"  {marker} {ts.timeframe}: {ts.total:+.4f} "
                f"(weight: {ts.weight:.0f}x)"
            )
        lines.append("")

        # Category breakdown (most significant contributors)
        lines.append("--- Key Signals ---")
        all_details: list[tuple[str, str, float, float]] = []
        for ts in tf_results:
            for cat in ts.categories.values():
                if abs(cat.score) > 0.05:
                    for d in cat.details:
                        all_details.append((ts.timeframe, cat.name, cat.score, d))

        # Sort by absolute category score, take top 8
        all_details.sort(key=lambda x: abs(x[2]), reverse=True)
        for tf, cat_name, score, detail in all_details[:10]:
            direction = "▲" if score > 0 else "▼"
            lines.append(f"  {direction} [{tf}] {detail}")

        # Entry/exit if available
        if entry_exit.get("entry_price"):
            lines.append("")
            lines.append("--- Trade Parameters ---")
            lines.append(f"  Entry: {entry_exit['entry_price']:.5f}")
            if entry_exit.get("stop_loss"):
                lines.append(f"  Stop Loss: {entry_exit['stop_loss']:.5f}")
            if entry_exit.get("take_profit_1"):
                lines.append(f"  Take Profit 1: {entry_exit['take_profit_1']:.5f}")
            if entry_exit.get("take_profit_2"):
                lines.append(f"  Take Profit 2: {entry_exit['take_profit_2']:.5f}")
            if entry_exit.get("risk_reward_ratio"):
                lines.append(f"  R:R (TP1): 1:{entry_exit['risk_reward_ratio']}")

        if decision == "WAIT":
            lines.append("")
            lines.append("No high-confidence setup detected. WAIT for clearer signals.")

        return "\n".join(lines)

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _bias_label(score: float) -> str:
        if score >= 0.50:
            return "Strong Buy"
        elif score >= BUY_THRESHOLD:
            return "Buy"
        elif score <= -0.50:
            return "Strong Sell"
        elif score <= SELL_THRESHOLD:
            return "Sell"
        return "Neutral"

    @staticmethod
    def _trend_summary(tf_results: list[TimeframeScore]) -> str:
        """Summarize overall trend from higher-TF trend categories."""
        higher_tf_scores = [
            ts.categories["trend"].score
            for ts in tf_results
            if ts.timeframe in HIGHER_TIMEFRAMES
        ]
        if not higher_tf_scores:
            return "Ranging"
        avg = sum(higher_tf_scores) / len(higher_tf_scores)
        if avg > 0.2:
            return "Bullish"
        elif avg < -0.2:
            return "Bearish"
        return "Ranging"

    @staticmethod
    def _risk_level(tf_results: list[TimeframeScore]) -> str:
        """Determine risk based on score variance across timeframes."""
        scores = [ts.total for ts in tf_results]
        if not scores:
            return "Medium"
        variance = sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)
        if variance < 0.05:
            return "Low"  # all TFs agree
        elif variance > 0.15:
            return "High"  # TFs disagree significantly
        return "Medium"
