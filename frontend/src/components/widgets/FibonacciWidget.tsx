import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import {
  api,
  ApiError,
  type FibonacciResponse,
  type SupportResistanceResponse,
} from '@/lib/api';
import { useDashboard } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, ErrorState, EmptyState, cn } from './shared';
import { formatSymbolLabel } from './LivePricesWidget';
import { formatDateTime, formatPrice } from '@/lib/format';

/**
 * Fibonacci — renders Fibonacci retracement levels and support/resistance for
 * the active symbol/timeframe (GET /api/v1/fibonacci/{symbol} and
 * GET /api/v1/support-resistance/{symbol}). The backend returns 404 with
 * "No indicator data found" for a valid symbol/timeframe that the indicator
 * calculator has not processed yet — that maps to a graceful empty state here,
 * matching the PR #11 "no data is not an error" contract.
 */
const FIB_LEVELS: { key: 'fib_236' | 'fib_382' | 'fib_500' | 'fib_618' | 'fib_786'; label: string }[] = [
  { key: 'fib_236', label: '23.6%' },
  { key: 'fib_382', label: '38.2%' },
  { key: 'fib_500', label: '50.0%' },
  { key: 'fib_618', label: '61.8%' },
  { key: 'fib_786', label: '78.6%' },
];

/** The backend stores fib_0/fib_1 as 0.0 placeholders — only the real levels are displayed. */
function fibLevels(data: FibonacciResponse): { key: string; label: string; price: number }[] {
  return FIB_LEVELS.map(({ key, label }) => ({ key, label, price: data[key] })).filter((l) => l.price > 0);
}

function isNoDataError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404;
}

export default function FibonacciWidget() {
  const { activeSymbol, activeTimeframe } = useDashboard();
  const [fib, setFib] = useState<FibonacciResponse | null>(null);
  const [sr, setSr] = useState<SupportResistanceResponse | null>(null);
  const [fibNoData, setFibNoData] = useState(false);
  const [srNoData, setSrNoData] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);
    setFibNoData(false);
    setSrNoData(false);
    const [fibRes, srRes] = await Promise.allSettled([
      api.getFibonacci(activeSymbol, activeTimeframe),
      api.getSupportResistance(activeSymbol, activeTimeframe),
    ]);
    if (requestIdRef.current !== requestId) return;

    let fibFailed = false;
    let srFailed = false;
    if (fibRes.status === 'fulfilled') {
      setFib(fibRes.value);
    } else if (isNoDataError(fibRes.reason)) {
      setFibNoData(true);
    } else {
      fibFailed = true;
    }
    if (srRes.status === 'fulfilled') {
      setSr(srRes.value);
    } else if (isNoDataError(srRes.reason)) {
      setSrNoData(true);
    } else {
      srFailed = true;
    }

    if (fibFailed && srFailed) {
      const first =
        ('reason' in fibRes ? fibRes.reason : null) ??
        ('reason' in srRes ? srRes.reason : null);
      const message =
        first instanceof ApiError
          ? first.detail
          : first instanceof Error
            ? first.message
            : 'Failed to load Fibonacci levels';
      setError(message);
      if (!(first instanceof ApiError && first.status === 401)) toast.error(message);
    }
    setIsLoading(false);
  }, [activeSymbol, activeTimeframe]);

  useEffect(() => {
    load();
    return () => {
      requestIdRef.current += 1;
    };
  }, [load]);

  const hasAnyData = fib !== null || sr !== null;
  const levels = fib ? fibLevels(fib) : [];
  const range = levels.length > 1
    ? Math.max(...levels.map((l) => l.price)) - Math.min(...levels.map((l) => l.price))
    : 0;
  const minPrice = levels.length > 0 ? Math.min(...levels.map((l) => l.price)) : 0;

  return (
    <WidgetCard
      title="Fibonacci"
      subtitle={`${formatSymbolLabel(activeSymbol)} · ${activeTimeframe} — retracement levels`}
      testId="fibonacci"
    >
      {isLoading && !hasAnyData ? (
        <WidgetSkeleton rows={7} />
      ) : error && !hasAnyData ? (
        <ErrorState message={error} onRetry={load} />
      ) : fibNoData && srNoData ? (
        <EmptyState
          message={`No Fibonacci or support/resistance data for ${formatSymbolLabel(activeSymbol)} ${activeTimeframe} yet — the indicator calculator is still warming up.`}
        />
      ) : (
        <div className="h-full flex flex-col gap-3 overflow-auto">
          {/* Fibonacci retracements */}
          <div className="shrink-0">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-forex-text-muted uppercase tracking-wider">Retracement levels</span>
              {fib && <span className="text-[10px] font-mono text-forex-text-muted">{formatDateTime(fib.timestamp)}</span>}
            </div>
            {fib === null ? (
              <p className="text-[11px] text-forex-text-muted">
                {fibNoData
                  ? 'Fibonacci levels not computed for this symbol/timeframe yet.'
                  : 'Fibonacci data unavailable right now.'}
              </p>
            ) : levels.length === 0 ? (
              <p className="text-[11px] text-forex-text-muted">Fibonacci levels not available for this market.</p>
            ) : (
              <div className="rounded-lg border border-white/5 bg-white/[0.02] overflow-hidden">
                {levels.map((level) => {
                  const position = range > 0 ? ((level.price - minPrice) / range) * 100 : 50;
                  return (
                    <div
                      key={level.key}
                      className="flex items-center justify-between gap-3 px-3 py-1.5 border-b border-white/[0.04] last:border-0"
                    >
                      <span className="text-[11px] text-forex-text-muted w-12">{level.label}</span>
                      <div className="flex-1 h-1 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-forex-cyan/60"
                          style={{ width: `${Math.min(100, Math.max(0, position))}%` }}
                        />
                      </div>
                      <span className="text-[11px] font-mono font-medium text-forex-text tabular-nums w-20 text-right">
                        {formatPrice(level.price)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          {/* Support / Resistance */}
          <div className="shrink-0">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-forex-text-muted uppercase tracking-wider">Support / Resistance</span>
              {sr && <span className="text-[10px] font-mono text-forex-text-muted">{formatDateTime(sr.timestamp)}</span>}
            </div>
            {sr === null ? (
              <p className="text-[11px] text-forex-text-muted">
                {srNoData
                  ? 'Support/resistance levels not computed for this symbol/timeframe yet.'
                  : 'Support/resistance data unavailable right now.'}
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {sr.support_levels.map((level, i) => (
                  <span
                    key={`s-${i}`}
                    className="px-2 py-0.5 rounded-md border border-forex-bullish/25 bg-forex-bullish/10 text-[10px] font-mono text-forex-bullish"
                    title={`Support ${i + 1}`}
                  >
                    S {formatPrice(level)}
                  </span>
                ))}
                {sr.resistance_levels.map((level, i) => (
                  <span
                    key={`r-${i}`}
                    className="px-2 py-0.5 rounded-md border border-forex-bearish/25 bg-forex-bearish/10 text-[10px] font-mono text-forex-bearish"
                    title={`Resistance ${i + 1}`}
                  >
                    R {formatPrice(level)}
                  </span>
                ))}
                {sr.support_levels.length === 0 && sr.resistance_levels.length === 0 && (
                  <p className="text-[11px] text-forex-text-muted">No levels detected on {activeTimeframe} yet.</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </WidgetCard>
  );
}
