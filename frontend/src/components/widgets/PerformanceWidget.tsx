import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type BacktestResultResponse, type BacktestRunSummary } from '@/lib/api';
import { WidgetCard, WidgetSkeleton, ErrorState, EmptyState, Sparkline, StatRow, cn } from './shared';
import { formatCurrency, formatDateTime, formatPercent } from '@/lib/format';
import { formatSymbolLabel } from './LivePricesWidget';

export default function PerformanceWidget() {
  const [runs, setRuns] = useState<BacktestRunSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<BacktestResultResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getBacktestRuns(5);
      if (requestIdRef.current !== requestId) return;
      setRuns(res.runs);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      const message = err instanceof ApiError ? err.detail : 'Failed to load backtest runs';
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

  const toggleDetail = async (runId: string) => {
    if (expandedId === runId) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(runId);
    setDetailLoading(true);
    try {
      const res = await api.getBacktestRun(runId);
      setDetail(res);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : 'Failed to load run detail';
      toast.error(message);
      setExpandedId(null);
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <WidgetCard
      title="Performance Dashboard"
      subtitle="Recent backtest runs — click a run for full detail"
      right={
        <button
          onClick={load}
          disabled={isLoading}
          title="Refresh runs"
          className="shrink-0 px-2 py-1 rounded-md text-[11px] text-forex-text-muted hover:text-forex-text hover:bg-white/5 border border-transparent transition-all disabled:opacity-50"
        >
          ↻
        </button>
      }
      testId="performance"
    >
      {isLoading && runs.length === 0 ? (
        <WidgetSkeleton rows={5} />
      ) : error && runs.length === 0 ? (
        <ErrorState message={error} onRetry={load} />
      ) : runs.length === 0 ? (
        <EmptyState message="No backtest runs yet — run a backtest from the backend API and summaries will appear here." />
      ) : (
        <div className="h-full overflow-auto">
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {runs.map((run) => {
              const netReturn =
                run.initial_balance > 0 ? ((run.final_balance - run.initial_balance) / run.initial_balance) * 100 : 0;
              const profitable = netReturn >= 0;
              const isExpanded = expandedId === run.id;
              return (
                <div
                  key={run.id}
                  className={cn(
                    'rounded-xl border transition-all',
                    isExpanded ? 'border-forex-cyan/30 bg-white/[0.03]' : 'border-white/5 bg-white/[0.02] hover:bg-white/[0.04]',
                  )}
                >
                  <button
                    onClick={() => void toggleDetail(run.id)}
                    className="w-full text-left px-4 py-3"
                    title="Click for full detail"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono text-xs font-semibold text-forex-text">{formatSymbolLabel(run.symbol)}</span>
                        <span className="px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-[9px] font-mono text-forex-text-dim">
                          {run.timeframe}
                        </span>
                      </div>
                      <span className="text-[10px] text-forex-text-muted shrink-0">
                        {formatDateTime(run.start_date)} → {formatDateTime(run.end_date)}
                      </span>
                    </div>
                    <div className="grid grid-cols-4 gap-2 mt-2 text-center">
                      <div>
                        <div className="text-[9px] uppercase text-forex-text-muted">Win rate</div>
                        <div className="text-xs font-mono font-semibold text-forex-text">{run.win_rate.toFixed(1)}%</div>
                      </div>
                      <div>
                        <div className="text-[9px] uppercase text-forex-text-muted">Profit factor</div>
                        <div className={cn('text-xs font-mono font-semibold', (run.profit_factor ?? 0) >= 1 ? 'text-forex-bullish' : 'text-forex-bearish')}>
                          {run.profit_factor !== null ? run.profit_factor.toFixed(2) : '—'}
                        </div>
                      </div>
                      <div>
                        <div className="text-[9px] uppercase text-forex-text-muted">Net return</div>
                        <div className={cn('text-xs font-mono font-semibold', profitable ? 'text-forex-bullish' : 'text-forex-bearish')}>
                          {formatPercent(netReturn)}
                        </div>
                      </div>
                      <div>
                        <div className="text-[9px] uppercase text-forex-text-muted">Trades</div>
                        <div className="text-xs font-mono font-semibold text-forex-text">{run.total_trades}</div>
                      </div>
                    </div>
                    {/* Final vs initial balance bar */}
                    <div className="mt-2">
                      <div className="flex justify-between text-[9px] text-forex-text-muted mb-1">
                        <span>{formatCurrency(run.initial_balance, 0)}</span>
                        <span className={profitable ? 'text-forex-bullish' : 'text-forex-bearish'}>
                          {formatCurrency(run.final_balance, 0)}
                        </span>
                      </div>
                      <div className="relative h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className={cn(
                            'absolute inset-y-0 left-0 rounded-full transition-all duration-700',
                            profitable ? 'bg-gradient-to-r from-forex-cyan to-forex-bullish' : 'bg-gradient-to-r from-forex-bearish to-forex-bearish/50',
                          )}
                          style={{ width: `${Math.min(100, Math.max(4, (run.final_balance / (run.initial_balance || 1)) * 100))}%` }}
                        />
                      </div>
                    </div>
                  </button>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="px-4 pb-4 border-t border-white/5 pt-3 fade-in">
                      {detailLoading ? (
                        <WidgetSkeleton rows={3} />
                      ) : detail ? (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                          <div>
                            <div className="text-[10px] uppercase tracking-widest text-forex-text-muted mb-1">Equity curve</div>
                            <div className="rounded-lg bg-forex-bg/60 border border-white/5 p-2 inline-block">
                              <Sparkline
                                data={detail.equity_curve.map((p) => p.balance)}
                                color={netReturn >= 0 ? '#00d4aa' : '#ff4d6a'}
                              />
                            </div>
                            <div className="rounded-lg bg-white/[0.02] border border-white/5 px-3 py-1 mt-2">
                              <StatRow label="Expectancy" value={formatCurrency(detail.expectancy)} />
                              <StatRow label="Max drawdown" value={formatPercent(detail.max_drawdown)} />
                              <StatRow label="Sharpe ratio" value={detail.sharpe_ratio !== null ? detail.sharpe_ratio.toFixed(2) : '—'} />
                              <StatRow label="Risk / trade" value={`${detail.risk_percentage.toFixed(2)}%`} />
                            </div>
                          </div>
                          <div>
                            <div className="text-[10px] uppercase tracking-widest text-forex-text-muted mb-1">Recent trades</div>
                            <div className="space-y-1 max-h-[140px] overflow-auto">
                              {detail.trades.slice(0, 6).map((t) => (
                                <div key={t.id} className="flex items-center justify-between text-[10px] font-mono border-b border-white/5 pb-1">
                                  <span>
                                    {t.direction} {formatSymbolLabel(t.symbol)}
                                  </span>
                                  <span className={t.pnl >= 0 ? 'text-forex-bullish' : 'text-forex-bearish'}>
                                    {t.pnl >= 0 ? '+' : ''}
                                    {formatCurrency(t.pnl)}
                                  </span>
                                </div>
                              ))}
                              {detail.trades.length === 0 && (
                                <p className="text-[10px] text-forex-text-muted">No trades in this run.</p>
                              )}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <p className="text-[10px] text-forex-text-muted">Could not load detail.</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </WidgetCard>
  );
}
