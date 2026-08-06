import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type DecisionResult } from '@/lib/api';
import { useDashboard } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, ErrorState, cn } from './shared';
import { formatPrice, formatQuantity } from '@/lib/format';

const DECISION_STYLES: Record<string, { badge: string; text: string; glow: string }> = {
  BUY: {
    badge: 'bg-forex-bullish/15 text-forex-bullish border-forex-bullish/40',
    text: 'text-forex-bullish',
    glow: 'shadow-[0_0_40px_rgba(0,212,170,0.15)]',
  },
  SELL: {
    badge: 'bg-forex-bearish/15 text-forex-bearish border-forex-bearish/40',
    text: 'text-forex-bearish',
    glow: 'shadow-[0_0_40px_rgba(255,77,106,0.15)]',
  },
  WAIT: {
    badge: 'bg-yellow-400/10 text-yellow-400 border-yellow-400/30',
    text: 'text-yellow-400',
    glow: 'shadow-[0_0_40px_rgba(250,204,21,0.1)]',
  },
};

export default function AIRecommendationWidget() {
  const { activeSymbol } = useDashboard();
  const [result, setResult] = useState<DecisionResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const runAnalysis = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getAIRecommendation(activeSymbol);
      if (requestIdRef.current !== requestId) return; // stale response
      setResult(data);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      const message =
        err instanceof ApiError ? err.detail : 'Analysis failed — please try again';
      setError(message);
      setResult(null);
      if (!(err instanceof ApiError && err.status === 401)) toast.error(message);
    } finally {
      if (requestIdRef.current === requestId) setIsLoading(false);
    }
  }, [activeSymbol]);

  // Auto-run when the active symbol changes.
  useEffect(() => {
    runAnalysis();
    return () => {
      requestIdRef.current += 1;
    };
  }, [runAnalysis]);

  const style = result ? DECISION_STYLES[result.decision] ?? DECISION_STYLES.WAIT : null;

  return (
    <WidgetCard
      title="AI Recommendation"
      subtitle={result ? `Analyzed ${result.created_at ? new Date(result.created_at).toLocaleString() : 'now'}` : undefined}
      right={
        <button
          onClick={runAnalysis}
          disabled={isLoading}
          className="shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-forex-bullish/15 text-forex-bullish border border-forex-bullish/30 hover:bg-forex-bullish/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.97]"
        >
          {isLoading ? 'Analyzing…' : '↻ Refresh Analysis'}
        </button>
      }
      testId="ai-recommendation"
    >
      {isLoading && !result ? (
        <div className="h-full flex items-center justify-center">
          <WidgetSkeleton rows={6} tall />
        </div>
      ) : error && !result ? (
        <ErrorState message={error} onRetry={runAnalysis} />
      ) : result && style ? (
        <div className="h-full flex flex-col gap-3 overflow-auto">
          {/* Decision badge */}
          <div className={cn('rounded-xl border p-4 text-center transition-all', style.badge, style.glow)}>
            <div className="text-[10px] uppercase tracking-widest text-forex-text-muted mb-1">
              {result.symbol} · {result.market_bias} · {result.risk_level} risk
            </div>
            <div className={cn('text-4xl font-extrabold tracking-tight', style.text)}>{result.decision}</div>
            <div className="mt-2 flex items-center justify-center gap-2">
              <div className="flex-1 max-w-[220px]">
                <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-forex-cyan to-forex-bullish transition-all duration-700"
                    style={{ width: `${Math.max(0, Math.min(100, result.confidence))}%` }}
                  />
                </div>
              </div>
              <span className="text-xs font-mono font-semibold text-forex-text">
                {result.confidence.toFixed(0)}% conf.
              </span>
            </div>
          </div>

          {/* Levels */}
          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              { label: 'Entry', value: result.entry_price !== null ? formatPrice(result.entry_price) : '—' },
              { label: 'SL', value: result.stop_loss !== null ? formatPrice(result.stop_loss) : '—' },
              { label: 'R/R', value: result.risk_reward_ratio !== null ? formatQuantity(result.risk_reward_ratio) : '—' },
              { label: 'TP1', value: result.take_profit_1 !== null ? formatPrice(result.take_profit_1) : '—' },
              { label: 'TP2', value: result.take_profit_2 !== null ? formatPrice(result.take_profit_2) : '—' },
              { label: 'Trend', value: result.trend },
            ].map((cell) => (
              <div key={cell.label} className="rounded-lg bg-white/[0.03] border border-white/5 px-2 py-2">
                <div className="text-[10px] text-forex-text-muted uppercase tracking-wide">{cell.label}</div>
                <div className="text-xs font-mono font-medium text-forex-text mt-0.5 truncate" title={cell.value}>
                  {cell.value}
                </div>
              </div>
            ))}
          </div>

          {/* Timeframe breakdown */}
          {result.timeframe_details.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-forex-text-muted mb-1.5">
                Timeframe contribution
              </div>
              <div className="flex flex-wrap gap-1.5">
                {result.timeframe_details.map((tf) => (
                  <span
                    key={tf.timeframe}
                    className={cn(
                      'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono border',
                      tf.score > 0
                        ? 'bg-forex-bullish/10 text-forex-bullish border-forex-bullish/25'
                        : tf.score < 0
                          ? 'bg-forex-bearish/10 text-forex-bearish border-forex-bearish/25'
                          : 'bg-white/5 text-forex-text-dim border-white/10',
                    )}
                  >
                    {tf.timeframe}
                    <span className="opacity-80">
                      {tf.score > 0 ? '+' : ''}
                      {tf.score.toFixed(1)} (w {tf.weight.toFixed(2)})
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Reasoning */}
          <div className="rounded-lg bg-white/[0.02] border border-white/5 p-3">
            <div className="text-[10px] uppercase tracking-widest text-forex-text-muted mb-1">Reasoning</div>
            <p className="text-xs leading-relaxed text-forex-text-dim whitespace-pre-wrap">{result.reasoning}</p>
          </div>
        </div>
      ) : null}
    </WidgetCard>
  );
}
