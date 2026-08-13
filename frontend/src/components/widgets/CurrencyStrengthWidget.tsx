import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type IndicatorResponse } from '@/lib/api';
import { useDashboard, SUPPORTED_SYMBOLS } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, ErrorState, EmptyState, cn } from './shared';
import { formatSymbolLabel } from './LivePricesWidget';

interface StrengthRow {
  symbol: string;
  name: string;
  rsi: number | null;
  strength: number; // -50..+50 (rsi - 50)
}

export default function CurrencyStrengthWidget() {
  const { setActiveSymbol, activeSymbol } = useDashboard();
  const [rows, setRows] = useState<StrengthRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const settled = await Promise.allSettled(
        SUPPORTED_SYMBOLS.map((code) => api.getLatestIndicator(code, 'H1')),
      );
      if (requestIdRef.current !== requestId) return;
      const next: StrengthRow[] = [];
      settled.forEach((res, i) => {
        const code = SUPPORTED_SYMBOLS[i];
        if (!code) return;
        if (res.status === 'fulfilled') {
          const ind: IndicatorResponse | null = res.value.indicator;
          // Valid symbol+timeframe with no indicator rows yet -> 200 + null.
          const rsi = ind === null ? null : ind.rsi;
          next.push({
            symbol: code,
            name: formatSymbolLabel(code),
            rsi,
            strength: rsi === null ? 0 : rsi - 50,
          });
        } else {
          next.push({ symbol: code, name: formatSymbolLabel(code), rsi: null, strength: 0 });
        }
      });
      // Strongest first.
      next.sort((a, b) => b.strength - a.strength);
      setRows(next);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      const message = err instanceof ApiError ? err.detail : 'Failed to load strength data';
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

  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.strength)), 15);

  return (
    <WidgetCard
      title="Currency Strength Meter"
      subtitle="H1 RSI-based relative strength across all symbols"
      testId="currency-strength"
    >
      {isLoading && rows.length === 0 ? (
        <WidgetSkeleton rows={10} />
      ) : error && rows.length === 0 ? (
        <ErrorState message={error} onRetry={load} />
      ) : rows.length === 0 ? (
        <EmptyState message="No indicator data available yet — run the backend so indicators get calculated." />
      ) : (
        <div className="h-full flex flex-col">
          <div className="flex-1 overflow-auto space-y-2 pr-1">
            {rows.map((row) => {
              const pct = (Math.abs(row.strength) / maxAbs) * 100;
              const strong = row.strength >= 0;
              const isActive = row.symbol === activeSymbol;
              return (
                <button
                  key={row.symbol}
                  onClick={() => setActiveSymbol(row.symbol)}
                  className={cn(
                    'w-full text-left group transition-all rounded-md px-1.5 py-1',
                    isActive ? 'bg-white/[0.04]' : 'hover:bg-white/[0.03]',
                  )}
                >
                  <div className="flex items-center justify-between text-[11px] mb-0.5">
                    <span className={cn('font-mono font-medium', isActive ? 'text-forex-bullish' : 'text-forex-text')}>
                      {row.name}
                    </span>
                    <span
                      className={cn(
                        'font-mono tabular-nums',
                        row.rsi === null ? 'text-forex-text-muted' : strong ? 'text-forex-bullish' : 'text-forex-bearish',
                      )}
                    >
                      {row.rsi === null ? '—' : `${row.rsi.toFixed(1)} · ${row.strength > 0 ? '+' : ''}${row.strength.toFixed(1)}`}
                    </span>
                  </div>
                  <div className="relative h-1.5 rounded-full bg-white/5 overflow-hidden">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-white/10" />
                    <div
                      className={cn(
                        'absolute h-full rounded-full transition-all duration-700',
                        strong
                          ? 'bg-gradient-to-r from-forex-bullish/40 to-forex-bullish'
                          : 'bg-gradient-to-l from-forex-bearish/40 to-forex-bearish',
                      )}
                      style={
                        strong
                          ? { left: '50%', width: `${Math.max(1.5, pct / 2)}%` }
                          : { right: '50%', width: `${Math.max(1.5, pct / 2)}%` }
                      }
                    />
                  </div>
                </button>
              );
            })}
          </div>
          <div className="flex items-center justify-between text-[10px] text-forex-text-muted mt-2 shrink-0">
            <span className="flex items-center gap-1">
              <span className="w-3 h-1 rounded-full bg-forex-bearish" /> Weak
            </span>
            <span className="flex items-center gap-1">
              Strong <span className="w-3 h-1 rounded-full bg-forex-bullish" />
            </span>
          </div>
        </div>
      )}
    </WidgetCard>
  );
}
