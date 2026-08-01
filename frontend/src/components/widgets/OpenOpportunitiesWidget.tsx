import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type RecommendationResponse } from '@/lib/api';
import { useDashboard } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, ErrorState, EmptyState, cn } from './shared';
import { formatPrice } from '@/lib/format';
import { formatSymbolLabel } from './LivePricesWidget';

const BADGE: Record<string, string> = {
  BUY: 'bg-forex-bullish/15 text-forex-bullish border-forex-bullish/40',
  SELL: 'bg-forex-bearish/15 text-forex-bearish border-forex-bearish/40',
  WAIT: 'bg-yellow-400/10 text-yellow-400 border-yellow-400/30',
};

export default function OpenOpportunitiesWidget() {
  const { setActiveSymbol, activeSymbol } = useDashboard();
  const [items, setItems] = useState<RecommendationResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getAIRecommendations(5);
      if (requestIdRef.current !== requestId) return;
      setItems(res.recommendations);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      const message = err instanceof ApiError ? err.detail : 'Failed to load recommendations';
      setError(message);
      if (!(err instanceof ApiError && err.status === 401)) toast.error(message);
    } finally {
      if (requestIdRef.current === requestId) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => {
      requestIdRef.current += 1;
    };
  }, [load]);

  return (
    <WidgetCard
      title="Open Opportunities"
      subtitle="Recent AI recommendations across markets"
      right={
        <button
          onClick={load}
          disabled={isLoading}
          title="Refresh recommendations"
          className="shrink-0 px-2 py-1 rounded-md text-[11px] text-forex-text-muted hover:text-forex-text hover:bg-white/5 border border-transparent transition-all disabled:opacity-50"
        >
          ↻
        </button>
      }
      testId="open-opportunities"
    >
      {isLoading && items.length === 0 ? (
        <WidgetSkeleton rows={5} />
      ) : error && items.length === 0 ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState message="No AI recommendations yet — run an analysis from the AI Recommendation widget and it will appear here." />
      ) : (
        <div className="h-full overflow-auto space-y-1.5 pr-1">
          {items.map((rec) => {
            const isActive = rec.symbol === activeSymbol;
            return (
              <button
                key={rec.id}
                onClick={() => setActiveSymbol(rec.symbol)}
                className={cn(
                  'w-full text-left rounded-lg border px-3 py-2 transition-all group',
                  isActive
                    ? 'border-forex-bullish/30 bg-forex-bullish-dim'
                    : 'border-white/5 bg-white/[0.02] hover:bg-white/[0.04]',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-xs font-semibold text-forex-text">
                      {formatSymbolLabel(rec.symbol)}
                    </span>
                    <span className={cn('px-1.5 py-0.5 rounded text-[9px] font-bold border', BADGE[rec.decision] ?? BADGE.WAIT)}>
                      {rec.decision}
                    </span>
                    <span className="text-[10px] font-mono text-forex-text-dim">
                      {rec.confidence.toFixed(0)}%
                    </span>
                  </div>
                  <span className="text-[10px] text-forex-text-muted shrink-0">
                    {new Date(rec.created_at).toLocaleDateString()}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1 text-[10px] font-mono text-forex-text-muted">
                  <span>
                    E <span className="text-forex-text-dim">{rec.entry_price !== null ? formatPrice(rec.entry_price) : '—'}</span>
                  </span>
                  <span>
                    SL <span className="text-forex-bearish/90">{rec.stop_loss !== null ? formatPrice(rec.stop_loss) : '—'}</span>
                  </span>
                  <span>
                    TP <span className="text-forex-bullish/90">{rec.take_profit_1 !== null ? formatPrice(rec.take_profit_1) : '—'}</span>
                  </span>
                  {rec.risk_reward_ratio !== null && (
                    <span className="ml-auto">
                      R/R <span className="text-forex-cyan">{rec.risk_reward_ratio.toFixed(2)}</span>
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </WidgetCard>
  );
}
