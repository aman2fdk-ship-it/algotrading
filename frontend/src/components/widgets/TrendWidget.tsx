import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type IndicatorResponse } from '@/lib/api';
import { useDashboard } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, ErrorState, EmptyState, MiniBar, StatRow, cn } from './shared';
import { formatPrice } from '@/lib/format';

type TrendDir = 'Bullish' | 'Bearish' | 'Neutral';

interface TrendSummary {
  direction: TrendDir;
  emaAlignment: 'Bullish' | 'Bearish' | 'Mixed';
  rsiSignal: string;
  adxSignal: string;
}

function analyzeTrend(ind: IndicatorResponse): TrendSummary {
  const { ema_20, ema_50, ema_200, rsi, adx, supertrend_direction } = ind;
  let emaAlignment: 'Bullish' | 'Bearish' | 'Mixed' = 'Mixed';
  if (ema_20 !== null && ema_50 !== null && ema_200 !== null) {
    if (ema_20 > ema_50 && ema_50 > ema_200) emaAlignment = 'Bullish';
    else if (ema_20 < ema_50 && ema_50 < ema_200) emaAlignment = 'Bearish';
  }

  let rsiSignal = 'Neutral';
  if (rsi !== null) {
    if (rsi >= 55) rsiSignal = 'Bullish';
    else if (rsi <= 45) rsiSignal = 'Bearish';
    if (rsi >= 70) rsiSignal = 'Overbought';
    else if (rsi <= 30) rsiSignal = 'Oversold';
  }

  let adxSignal = 'Weak';
  if (adx !== null) {
    adxSignal = adx >= 40 ? 'Strong trend' : adx >= 25 ? 'Trending' : 'Ranging';
  }

  const supertrendBull = supertrend_direction === 1 || supertrend_direction === null;
  let votes = 0;
  if (emaAlignment === 'Bullish') votes += 1;
  if (emaAlignment === 'Bearish') votes -= 1;
  if (supertrendBull && supertrend_direction !== null) votes += 1;
  if (!supertrendBull && supertrend_direction !== null) votes -= 1;
  if (rsi !== null && rsi >= 55) votes += 1;
  if (rsi !== null && rsi <= 45) votes -= 1;

  const direction: TrendDir = votes > 0 ? 'Bullish' : votes < 0 ? 'Bearish' : 'Neutral';
  return { direction, emaAlignment, rsiSignal, adxSignal };
}

export default function TrendWidget() {
  const { activeSymbol, activeTimeframe } = useDashboard();
  const [indicator, setIndicator] = useState<IndicatorResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getLatestIndicator(activeSymbol, activeTimeframe);
      if (requestIdRef.current !== requestId) return;
      setIndicator(res.indicator);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      const message =
        err instanceof ApiError ? err.detail : 'Failed to load indicator data';
      setError(message);
      setIndicator(null);
      if (!(err instanceof ApiError && err.status === 401)) toast.error(message);
    } finally {
      if (requestIdRef.current === requestId) setIsLoading(false);
    }
  }, [activeSymbol, activeTimeframe]);

  useEffect(() => {
    load();
    return () => {
      requestIdRef.current += 1;
    };
  }, [load]);

  const summary = indicator ? analyzeTrend(indicator) : null;

  const directionStyles: Record<TrendDir, string> = {
    Bullish: 'bg-forex-bullish/15 text-forex-bullish border-forex-bullish/40',
    Bearish: 'bg-forex-bearish/15 text-forex-bearish border-forex-bearish/40',
    Neutral: 'bg-white/5 text-forex-text-dim border-white/15',
  };

  return (
    <WidgetCard
      title="Current Trend"
      subtitle={`${activeSymbol} · ${activeTimeframe} · indicators`}
      testId="trend"
    >
      {isLoading && !indicator ? (
        <WidgetSkeleton rows={5} />
      ) : error && !indicator ? (
        <ErrorState message={error} onRetry={load} />
      ) : indicator && summary ? (
        <div className="h-full flex flex-col gap-3 overflow-auto">
          {/* Direction */}
          <div className="flex items-center justify-between">
            <span className={cn('px-4 py-1.5 rounded-lg border text-sm font-bold tracking-wide', directionStyles[summary.direction])}>
              {summary.direction}
            </span>
            <div className="text-right">
              <div className="text-[10px] text-forex-text-muted uppercase tracking-wider">Last close</div>
              <div className="text-sm font-mono font-semibold text-forex-text">
                {indicator.ema_20 !== null ? formatPrice(indicator.ema_20) : '—'}
              </div>
            </div>
          </div>

          {/* Momentum mini bars */}
          <div className="space-y-2">
            {indicator.rsi !== null && (
              <div>
                <div className="flex justify-between text-[10px] mb-1">
                  <span className="text-forex-text-muted">RSI Momentum</span>
                  <span className={cn('font-mono', indicator.rsi >= 70 ? 'text-forex-bearish' : indicator.rsi <= 30 ? 'text-forex-bullish' : 'text-forex-text')}>
                    {indicator.rsi.toFixed(1)} · {summary.rsiSignal}
                  </span>
                </div>
                <MiniBar value={indicator.rsi} max={100} min={0} />
              </div>
            )}
            {indicator.adx !== null && (
              <div>
                <div className="flex justify-between text-[10px] mb-1">
                  <span className="text-forex-text-muted">ADX Trend Strength</span>
                  <span className="font-mono text-forex-text">
                    {indicator.adx.toFixed(1)} · {summary.adxSignal}
                  </span>
                </div>
                <MiniBar value={Math.min(indicator.adx, 60)} max={60} min={0} reverse />
              </div>
            )}
            {indicator.macd_histogram !== null && indicator.macd_histogram !== 0 && (
              <div>
                <div className="flex justify-between text-[10px] mb-1">
                  <span className="text-forex-text-muted">MACD Histogram</span>
                  <span className={cn('font-mono', indicator.macd_histogram > 0 ? 'text-forex-bullish' : 'text-forex-bearish')}>
                    {indicator.macd_histogram > 0 ? '+' : ''}
                    {indicator.macd_histogram.toFixed(5)} {indicator.macd_histogram > 0 ? '↑' : '↓'}
                  </span>
                </div>
                <div className="relative w-full rounded-full bg-white/5 overflow-hidden" style={{ height: 4 }}>
                  <div className="absolute inset-y-0 left-1/2 w-px bg-white/10" />
                  <div
                    className={cn(
                      'absolute h-full rounded-full transition-all duration-500',
                      indicator.macd_histogram > 0 ? 'bg-forex-bullish/70' : 'bg-forex-bearish/70',
                    )}
                    style={{
                      left: indicator.macd_histogram > 0 ? '50%' : undefined,
                      right: indicator.macd_histogram > 0 ? undefined : '50%',
                      width: `${Math.min(50, Math.abs(indicator.macd_histogram) * 2000)}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Key levels */}
          <div className="rounded-lg bg-white/[0.02] border border-white/5 px-3 py-1">
            <StatRow
              label="EMA 20 / 50 / 200"
              value={
                <span className={summary.emaAlignment === 'Bullish' ? 'text-forex-bullish' : summary.emaAlignment === 'Bearish' ? 'text-forex-bearish' : 'text-forex-text-dim'}>
                  {indicator.ema_20?.toFixed(4) ?? '—'} / {indicator.ema_50?.toFixed(4) ?? '—'} /{' '}
                  {indicator.ema_200?.toFixed(4) ?? '—'}
                </span>
              }
            />
            <StatRow
              label="EMA alignment"
              value={summary.emaAlignment}
              valueClass={summary.emaAlignment === 'Bullish' ? 'text-forex-bullish' : summary.emaAlignment === 'Bearish' ? 'text-forex-bearish' : 'text-forex-text-dim'}
            />
            {indicator.atr !== null && <StatRow label="ATR (volatility)" value={indicator.atr.toFixed(5)} />}
            {indicator.bb_middle !== null && indicator.bb_upper !== null && (
              <StatRow label="Bollinger bands" value={`${indicator.bb_lower?.toFixed(4) ?? '—'} / ${indicator.bb_middle.toFixed(4)} / ${indicator.bb_upper.toFixed(4)}`} />
            )}
            {indicator.swing_high !== null && (
              <StatRow label="Swing high / low" value={`${indicator.swing_high.toFixed(4)} / ${indicator.swing_low?.toFixed(4) ?? '—'}`} />
            )}
          </div>
        </div>
      ) : (
        <EmptyState message="No indicator data yet — the indicator calculator is still warming up." />
      )}
    </WidgetCard>
  );
}
