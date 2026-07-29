"""AI Decision Engine API Router — BUY/SELL/WAIT recommendations."""

import json
import logging
from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.ai_recommendation import AIRecommendation
from app.repositories.indicator_repository import IndicatorRepository
from app.repositories.smc_repository import SMCRepository
from app.repositories.candle_repository import CandleRepository
from app.repositories.ai_recommendation_repo import AIRecommendationRepository
from app.schemas.ai import (
    AnalyzeRequest,
    AnalyzeBatchRequest,
    DecisionResult,
    RecommendationResponse,
    RecommendationListResponse,
    TimeframeScoreDetail,
)
from app.services.ai_decision import AIDecisionService
from app.services.mt5_client import SUPPORTED_SYMBOLS
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ai"])


def _build_service(db: AsyncSession) -> AIDecisionService:
    """Construct an AIDecisionService with real repositories."""
    return AIDecisionService(
        indicator_repo=IndicatorRepository(db),
        smc_repo=SMCRepository(db),
        candle_repo=CandleRepository(db),
        recommendation_repo=AIRecommendationRepository(db),
    )


def _serialize_recommendation(rec: AIRecommendation) -> RecommendationResponse:
    """Convert DB model to response schema, parsing JSON fields."""
    tf_scores: dict[str, float] = {}
    try:
        tf_scores = json.loads(rec.timeframe_scores)
    except (json.JSONDecodeError, TypeError):
        pass

    return RecommendationResponse(
        id=rec.id,
        symbol=rec.symbol,
        decision=rec.decision,
        confidence=rec.confidence,
        entry_price=rec.entry_price,
        stop_loss=rec.stop_loss,
        take_profit_1=rec.take_profit_1,
        take_profit_2=rec.take_profit_2,
        risk_reward_ratio=rec.risk_reward_ratio,
        trend=rec.trend,
        market_bias=rec.market_bias,
        risk_level=rec.risk_level,
        reasoning=rec.reasoning,
        timeframe_scores=tf_scores,
        created_at=rec.created_at,
    )


# ── Analyze (single) ────────────────────────────────────────────────────────────

@router.post("/ai/analyze", response_model=DecisionResult)
async def analyze_symbol(
    body: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Run a full AI analysis on a single symbol and return BUY/SELL/WAIT.

    This end-to-end analysis combines technical indicators, SMC/ICT patterns,
    volume/volatility, market structure, and multi-timeframe analysis into a
    single trading decision with reasoning, entry, SL, and TP levels.
    """
    symbol = body.symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported. Supported: {SUPPORTED_SYMBOLS}",
        )

    service = _build_service(db)
    try:
        result = await service.analyze_and_save(symbol)
    except Exception as e:
        logger.exception("AI analysis failed for %s: %s", symbol, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}",
        )

    return DecisionResult(
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
        timeframe_scores=result.timeframe_scores,
        timeframe_details=[
            TimeframeScoreDetail(**d) for d in result.timeframe_details
        ],
        created_at=result.created_at,
    )


# ── Analyze Batch ───────────────────────────────────────────────────────────────

@router.post("/ai/analyze-batch", response_model=list[DecisionResult])
async def analyze_batch(
    body: AnalyzeBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Run AI analysis on multiple symbols at once."""
    results: list[DecisionResult] = []
    service = _build_service(db)

    for sym in body.symbols:
        symbol = sym.upper()
        if symbol not in SUPPORTED_SYMBOLS:
            results.append(DecisionResult(
                symbol=symbol,
                decision="ERROR",
                confidence=0.0,
                reasoning=f"Symbol '{symbol}' is not supported.",
            ))
            continue

        try:
            result = await service.analyze_and_save(symbol)
            results.append(DecisionResult(
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
                timeframe_scores=result.timeframe_scores,
                timeframe_details=[
                    TimeframeScoreDetail(**d) for d in result.timeframe_details
                ],
                created_at=result.created_at,
            ))
        except Exception as e:
            logger.exception("Batch AI analysis failed for %s: %s", symbol, e)
            results.append(DecisionResult(
                symbol=symbol,
                decision="ERROR",
                confidence=0.0,
                reasoning=f"Analysis error: {str(e)}",
            ))

    return results


# ── Latest Recommendation ───────────────────────────────────────────────────────

@router.get(
    "/ai/recommendation/{symbol}",
    response_model=RecommendationResponse,
)
async def get_latest_recommendation(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the most recent AI recommendation for a symbol."""
    symbol = symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' is not supported.",
        )

    repo = AIRecommendationRepository(db)
    rec = await repo.get_latest(symbol)

    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No recommendations found for {symbol}. Run /ai/analyze first.",
        )

    return _serialize_recommendation(rec)


# ── Recent Recommendations ──────────────────────────────────────────────────────

@router.get(
    "/ai/recommendations",
    response_model=RecommendationListResponse,
)
async def get_recent_recommendations(
    limit: int = Query(default=10, ge=1, le=50),
    symbol: str | None = Query(default=None, description="Optional symbol filter"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get recent AI recommendations, optionally filtered by symbol."""
    repo = AIRecommendationRepository(db)

    if symbol:
        symbol = symbol.upper()
        if symbol not in SUPPORTED_SYMBOLS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{symbol}' is not supported.",
            )
        records = await repo.get_by_symbol(symbol, limit=limit)
    else:
        records = await repo.get_recent(limit=limit)

    return RecommendationListResponse(
        recommendations=[_serialize_recommendation(r) for r in records],
        count=len(records),
    )
