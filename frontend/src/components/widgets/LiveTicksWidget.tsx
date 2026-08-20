import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, type PriceResponse, type TickResponse } from '@/lib/api';
import { useDashboard } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, ErrorState, EmptyState, cn } from './shared';
import { formatSymbolLabel } from './LivePricesWidget';
import { formatPrice, formatTime } from '@/lib/format';

/**
 * Live Ticks — real-time price panel for the active symbol.
 * Polls the latest bid/ask/spread (GET /api/v1/price/{symbol}) on a short
 * interval and renders the most recent ticks (GET /api/v1/ticks/{symbol})
 * as a scrolling history. All data comes from the backend — no mock values.
 *
 * Empty handling (PR #11 contract): a valid symbol with no stored ticks returns
 * 200 + an empty list from /ticks and 503 from /price — that is the "no data
 * yet" state and renders a graceful empty state, never placeholder data.
 * Only a failed ticks fetch (backend down) renders the error state.
 */
const PRICE_POLL_MS = 3000;
const TICKS_POLL_MS = 5000;
const TICKS_LIMIT = 30;

interface PriceSnapshot extends PriceResponse {
  flash: 'up' | 'down' | null;
}

export default function LiveTicksWidget() {
  const { activeSymbol } = useDashboard();
  const [price, setPrice] = useState<PriceSnapshot | null>(null);
  const [ticks, setTicks] = useState<TickResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const mountedRef = useRef(true);
  const prevBidRef = useRef<number | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadPrice = useCallback(async () => {
    try {
      const p = await api.getPrice(activeSymbol);
      if (!mountedRef.current) return;
      setPrice((prev) => {
        const prevBid = prev?.bid ?? prevBidRef.current;
        const flash: 'up' | 'down' | null =
          prevBid === null || p.bid === prevBid ? null : p.bid > prevBid ? 'up' : 'down';
        prevBidRef.current = p.bid;
        return { ...p, flash };
      });
      setLastUpdated(new Date());
    } catch {
      // A missing/503 price is not an error for this widget: the ticks history
      // is the primary content and the price panel simply shows '—'.
    } finally {
      if (mountedRef.current) setIsLoading(false);
    }
  }, [activeSymbol]);

  const loadTicks = useCallback(async () => {
    try {
      const res = await api.getTicks(activeSymbol, TICKS_LIMIT);
      if (!mountedRef.current) return;
      // Backend returns the latest N ticks in chronological order — show
      // newest first for a live ticker feel.
      setTicks([...res.ticks].reverse());
      setError(null);
    } catch (err) {
      if (!mountedRef.current || (err instanceof ApiError && err.status === 401)) return;
      // A failed refresh keeps the last known history; surface the error only
      // when there is nothing to show at all.
      setError((prev) => prev ?? (err instanceof ApiError ? err.detail : 'Failed to load ticks'));
    } finally {
      if (mountedRef.current) setIsLoading(false);
    }
  }, [activeSymbol]);

  useEffect(() => {
    // Reset transient state when the active symbol changes.
    setError(null);
    setTicks([]);
    prevBidRef.current = null;
    setIsLoading(true);
    void loadPrice();
    void loadTicks();
    const priceId = window.setInterval(loadPrice, PRICE_POLL_MS);
    const ticksId = window.setInterval(loadTicks, TICKS_POLL_MS);
    return () => {
      window.clearInterval(priceId);
      window.clearInterval(ticksId);
    };
  }, [activeSymbol, loadPrice, loadTicks]);

  const retry = useCallback(() => {
    setError(null);
    setIsLoading(true);
    void loadPrice();
    void loadTicks();
  }, [loadPrice, loadTicks]);

  const hasData = price !== null || ticks.length > 0;

  return (
    <WidgetCard
      title="Live Ticks"
      subtitle={`${formatSymbolLabel(activeSymbol)} · latest price + tick history`}
      testId="live-ticks"
      right={
        lastUpdated ? (
          <span className="text-[10px] font-mono text-forex-text-muted">{formatTime(lastUpdated.toISOString())}</span>
        ) : undefined
      }
    >
      {isLoading && !hasData ? (
        <WidgetSkeleton rows={6} />
      ) : error && !hasData ? (
        <ErrorState message={error} onRetry={retry} />
      ) : !hasData ? (
        <EmptyState message={`No live tick data for ${formatSymbolLabel(activeSymbol)} yet — the feed is still warming up.`} />
      ) : (
        <div className="h-full flex flex-col gap-3 overflow-auto">
          {/* Latest bid/ask/spread snapshot */}
          <div className="rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3 shrink-0">
            <div className="flex items-end justify-between gap-4">
              <div>
                <div className="text-[10px] text-forex-text-muted uppercase tracking-wider">Bid</div>
                <div
                  className={cn(
                    'text-2xl font-mono font-bold tabular-nums transition-colors',
                    price?.flash === 'up' && 'text-forex-bullish price-flash-up',
                    price?.flash === 'down' && 'text-forex-bearish price-flash-down',
                  )}
                >
                  {price ? formatPrice(price.bid) : '—'}
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] text-forex-text-muted uppercase tracking-wider">Ask</div>
                <div className="text-xl font-mono font-semibold tabular-nums text-forex-text">
                  {price ? formatPrice(price.ask) : '—'}
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] text-forex-text-muted uppercase tracking-wider">Spread</div>
                <div className="text-xl font-mono font-semibold tabular-nums text-forex-cyan">
                  {price && price.spread > 0 ? price.spread : '—'}
                </div>
              </div>
            </div>
          </div>
          {/* Tick history */}
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="flex items-center justify-between text-[10px] text-forex-text-muted uppercase tracking-wider mb-1 shrink-0">
              <span>Recent ticks</span>
              <span>{ticks.length} shown</span>
            </div>
            <div className="flex-1 overflow-auto -mx-1 px-1">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-forex-bg/80 backdrop-blur-sm z-10">
                  <tr className="text-forex-text-muted border-b border-forex-border text-[10px]">
                    <th className="text-left py-1.5 font-medium">Time</th>
                    <th className="text-right py-1.5 font-medium">Bid</th>
                    <th className="text-right py-1.5 font-medium">Ask</th>
                    <th className="text-right py-1.5 font-medium">Sprd</th>
                    <th className="text-right py-1.5 font-medium">Vol</th>
                  </tr>
                </thead>
                <tbody>
                  {ticks.map((t, i) => (
                    <tr key={`${t.timestamp}-${i}`} className="border-b border-forex-border/40 font-mono tabular-nums">
                      <td className="py-1 pr-2 text-forex-text-muted whitespace-nowrap">{formatTime(t.timestamp)}</td>
                      <td className="py-1 pr-2 text-right text-forex-text">{formatPrice(t.bid)}</td>
                      <td className="py-1 pr-2 text-right text-forex-text-dim">{formatPrice(t.ask)}</td>
                      <td className="py-1 pr-2 text-right text-forex-text-muted">{t.spread}</td>
                      <td className="py-1 text-right text-forex-text-muted">{t.volume}</td>
                    </tr>
                  ))}
                  {ticks.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-3 text-center text-forex-text-muted">
                        No tick history yet — waiting for the next tick.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </WidgetCard>
  );
}
