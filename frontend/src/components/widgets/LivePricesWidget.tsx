import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type SymbolResponse, type PriceResponse } from '@/lib/api';
import { useDashboard, SUPPORTED_SYMBOLS } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, ErrorState, EmptyState, cn } from './shared';
import { formatPrice, formatPercent } from '@/lib/format';

interface PriceRow {
  symbol: string;
  name: string;
  bid: number;
  ask: number;
  spread: number;
  changePct: number | null;
  prevBid: number | null;
  flash: 'up' | 'down' | null;
}

/** "EURUSD" → "EUR/USD", "BTCUSD" → "BTC/USD". */
export function formatSymbolLabel(code: string): string {
  if (code.length === 6) return `${code.slice(0, 3)}/${code.slice(3)}`;
  return code;
}

const PRICE_POLL_MS = 5000;
const CHANGE_POLL_MS = 30000;

export default function LivePricesWidget() {
  const { activeSymbol, setActiveSymbol } = useDashboard();
  const [rows, setRows] = useState<Record<string, PriceRow>>({});
  const [symbols, setSymbols] = useState<SymbolResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fetchPrices = useCallback(async () => {
    const codes = SUPPORTED_SYMBOLS.length > 0 ? SUPPORTED_SYMBOLS : symbols.map((s) => s.code);
    const settled = await Promise.allSettled(codes.map((code) => api.getPrice(code)));
    setRows((prev) => {
      const next: Record<string, PriceRow> = { ...prev };
      settled.forEach((result, i) => {
        const code = codes[i];
        if (!code) return;
        if (result.status === 'fulfilled') {
          const price: PriceResponse = result.value;
          const existing = prev[code];
          const prevBid = existing?.bid ?? null;
          let flash: 'up' | 'down' | null = null;
          if (prevBid !== null && price.bid !== prevBid) {
            flash = price.bid > prevBid ? 'up' : 'down';
          }
          next[code] = {
            symbol: code,
            name: existing?.name ?? formatSymbolLabel(code),
            bid: price.bid,
            ask: price.ask,
            spread: price.spread,
            changePct: existing?.changePct ?? null,
            prevBid,
            flash,
          };
        } else {
          // Keep the previous row so the list stays stable during outages.
          if (!prev[code]) {
            next[code] = {
              symbol: code,
              name: formatSymbolLabel(code),
              bid: 0,
              ask: 0,
              spread: 0,
              changePct: null,
              prevBid: null,
              flash: null,
            };
          }
        }
      });
      return next;
    });
    setLastUpdated(new Date());
    if (mountedRef.current) setHasLoaded(true);
  }, [symbols]);

  const fetchChanges = useCallback(async () => {
    const codes = SUPPORTED_SYMBOLS.length > 0 ? SUPPORTED_SYMBOLS : symbols.map((s) => s.code);
    const settled = await Promise.allSettled(
      codes.map((code) => api.getCandles(code, 'H1', 3)),
    );
    setRows((prev) => {
      const next: Record<string, PriceRow> = { ...prev };
      settled.forEach((result, i) => {
        const code = codes[i];
        if (!code) return;
        const existing = next[code];
        if (!existing) return;
        if (result.status === 'fulfilled' && result.value.candles.length >= 2) {
          const candles = result.value.candles;
          const last = candles[candles.length - 1];
          const prevC = candles[candles.length - 2];
          if (last && prevC && prevC.close > 0) {
            const changePct = ((last.close - prevC.close) / prevC.close) * 100;
            next[code] = { ...existing, changePct };
          }
        }
      });
      return next;
    });
  }, [symbols]);

  const loadSymbols = useCallback(async () => {
    try {
      const res = await api.getSymbols();
      const enabled = res.symbols.filter((s) => s.enabled);
      const ordered = SUPPORTED_SYMBOLS.map(
        (code) => enabled.find((s) => s.code === code) ?? { code, name: '', asset_type: 'forex', pip_size: 0, digits: 5, enabled: true },
      );
      setSymbols(ordered);
      // Seed rows with names so headers render immediately.
      setRows((prev) => {
        const next: Record<string, PriceRow> = { ...prev };
        ordered.forEach((s) => {
          if (!next[s.code]) {
            next[s.code] = {
              symbol: s.code,
              name: s.name || formatSymbolLabel(s.code),
              bid: 0,
              ask: 0,
              spread: 0,
              changePct: null,
              prevBid: null,
              flash: null,
            };
          }
        });
        return next;
      });
      setError(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : 'Failed to load symbols';
      setError(message);
      // Stop the loading skeleton so the error state becomes visible.
      setIsLoading(false);
      if (!(err instanceof ApiError && err.status === 401)) toast.error(message);
    }
  }, []);

  useEffect(() => {
    loadSymbols();
  }, [loadSymbols]);

  useEffect(() => {
    if (symbols.length === 0) return;
    const loadAll = () => {
      Promise.allSettled([fetchPrices(), fetchChanges()]).then(() => {
        if (mountedRef.current) {
          setIsLoading(false);
          setHasLoaded(true);
        }
      });
    };
    loadAll();
    const priceTimer = setInterval(fetchPrices, PRICE_POLL_MS);
    const changeTimer = setInterval(fetchChanges, CHANGE_POLL_MS);
    return () => {
      clearInterval(priceTimer);
      clearInterval(changeTimer);
    };
  }, [symbols, fetchPrices, fetchChanges]);

  const orderedRows = SUPPORTED_SYMBOLS.map((code) => rows[code]).filter(
    (r): r is PriceRow => Boolean(r),
  );
  const activeName = rows[activeSymbol]?.name ?? formatSymbolLabel(activeSymbol);

  return (
    <WidgetCard
      title="Live Forex Prices"
      subtitle={lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : undefined}
      right={
        <span
          className={cn(
            'shrink-0 w-2 h-2 rounded-full self-center',
            isLoading ? 'bg-yellow-400/70 animate-pulse' : 'bg-forex-bullish animate-pulse-slow',
          )}
        />
      }
      testId="live-prices"
    >
      {isLoading && !hasLoaded ? (
        <WidgetSkeleton rows={10} />
      ) : error && orderedRows.length === 0 ? (
        <ErrorState message={error} onRetry={() => { loadSymbols(); }} />
      ) : orderedRows.length === 0 ? (
        <EmptyState message="No price data available yet — start the backend and MT5 to see live prices." />
      ) : (
        <div className="h-full flex flex-col">
          <div className="flex-1 overflow-auto -mx-1 px-1">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-forex-bg/80 backdrop-blur-sm z-10">
                <tr className="text-forex-text-muted border-b border-forex-border">
                  <th className="text-left py-2 font-medium">Symbol</th>
                  <th className="text-right py-2 font-medium">Bid</th>
                  <th className="text-right py-2 font-medium">Ask</th>
                  <th className="text-right py-2 font-medium">Spread</th>
                  <th className="text-right py-2 font-medium">Change</th>
                </tr>
              </thead>
              <tbody>
                {orderedRows.map((row) => {
                  const isActive = row.symbol === activeSymbol;
                  const up = (row.changePct ?? 0) >= 0;
                  return (
                    <tr
                      key={row.symbol}
                      onClick={() => setActiveSymbol(row.symbol)}
                      className={cn(
                        'border-b border-forex-border/50 cursor-pointer select-none',
                        'hover:bg-white/[0.03] transition-colors',
                        isActive && 'bg-forex-bullish-dim',
                        row.flash === 'up' && 'price-flash-up',
                        row.flash === 'down' && 'price-flash-down',
                      )}
                      title={`Select ${row.name}`}
                    >
                      <td className="py-2 pr-2 font-mono font-medium text-forex-text whitespace-nowrap">
                        <span className={cn('inline-flex items-center gap-1.5', isActive && 'text-forex-bullish')}>
                          <span
                            className={cn(
                              'w-1.5 h-1.5 rounded-full',
                              isActive ? 'bg-forex-bullish' : 'bg-white/15',
                            )}
                          />
                          {row.name}
                        </span>
                      </td>
                      <td
                        className={cn(
                          'py-2 text-right font-mono tabular-nums transition-colors',
                          row.flash === 'up' && 'text-forex-bullish',
                          row.flash === 'down' && 'text-forex-bearish',
                        )}
                      >
                        {row.bid > 0 ? formatPrice(row.bid) : '—'}
                      </td>
                      <td className="py-2 text-right font-mono tabular-nums text-forex-text-dim">
                        {row.ask > 0 ? formatPrice(row.ask) : '—'}
                      </td>
                      <td className="py-2 text-right font-mono tabular-nums text-forex-text-muted">
                        {row.spread > 0 ? row.spread.toFixed(1) : '—'}
                      </td>
                      <td
                        className={cn(
                          'py-2 text-right font-mono font-medium tabular-nums',
                          row.changePct === null
                            ? 'text-forex-text-muted'
                            : up
                              ? 'text-forex-bullish'
                              : 'text-forex-bearish',
                        )}
                      >
                        {row.changePct === null ? '—' : formatPercent(row.changePct)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-forex-text-muted mt-2 text-center shrink-0">
            Active: <span className="font-mono text-forex-bullish">{activeName}</span> · Refreshes every 5s ·
            Advisory only
          </p>
        </div>
      )}
    </WidgetCard>
  );
}
