import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type RecommendationResponse, type BacktestRunSummary, type BacktestResultResponse, type DecisionResult } from '@/lib/api';
import { useDashboard, type SymbolCode } from '@/contexts/DashboardContext';
import Sidebar from '@/components/Sidebar';
import TopBar from '@/components/TopBar';
import { WidgetCard, WidgetSkeleton, ErrorState, EmptyState, cn, MiniBar } from '@/components/widgets/shared';
import { formatPrice, formatPercent, formatCurrency, formatDateTime, parseNumber } from '@/lib/format';

const DECISION_STYLES: Record<string, { badge: string; text: string }> = {
  BUY: { badge: 'bg-forex-bullish/15 text-forex-bullish border-forex-bullish/40', text: 'text-forex-bullish' },
  SELL: { badge: 'bg-forex-bearish/15 text-forex-bearish border-forex-bearish/40', text: 'text-forex-bearish' },
  WAIT: { badge: 'bg-yellow-400/10 text-yellow-400 border-yellow-400/30', text: 'text-yellow-400' },
  ERROR: { badge: 'bg-red-500/10 text-red-400 border-red-500/30', text: 'text-red-400' },
};

export default function SignalDashboardPage() {
  const { activeSymbol } = useDashboard();

  // Latest AI recommendation (from a live /ai/analyze run)
  const [latest, setLatest] = useState<DecisionResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  // Persisted signals + backtest runs
  const [recommendations, setRecommendations] = useState<RecommendationResponse[]>([]);
  const [recLoading, setRecLoading] = useState(true);
  const [recError, setRecError] = useState<string | null>(null);

  const [runs, setRuns] = useState<BacktestRunSummary[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [lastBacktest, setLastBacktest] = useState<BacktestResultResponse | null>(null);

  // Backtest form
  const [btSymbol, setBtSymbol] = useState(activeSymbol);
  const [btTimeframe, setBtTimeframe] = useState('H1');
  const [btBalance, setBtBalance] = useState('10000');
  const [btRisk, setBtRisk] = useState('1.0');
  const [btRunning, setBtRunning] = useState(false);
  const [btError, setBtError] = useState<string | null>(null);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const loadRecommendations = useCallback(async () => {
    setRecLoading(true);
    setRecError(null);
    try {
      const data = await api.getAIRecommendations(6);
      if (mounted.current) {
        setRecommendations(data.recommendations);
        setRecLoading(false);
      }
    } catch (err) {
      if (mounted.current) {
        const msg = err instanceof ApiError ? err.detail : 'Could not load AI signals';
        setRecError(msg);
        setRecLoading(false);
        if (!(err instanceof ApiError && err.status === 401)) toast.error(msg);
      }
    }
  }, []);

  const loadRuns = useCallback(async () => {
    setRunsLoading(true);
    setRunsError(null);
    try {
      const data = await api.getBacktestRuns(6);
      if (mounted.current) {
        setRuns(data.runs);
        setRunsLoading(false);
      }
    } catch (err) {
      if (mounted.current) {
        const msg = err instanceof ApiError ? err.detail : 'Could not load backtest runs';
        setRunsError(msg);
        setRunsLoading(false);
        if (!(err instanceof ApiError && err.status === 401)) toast.error(msg);
      }
    }
  }, []);

  useEffect(() => {
    loadRecommendations();
    loadRuns();
  }, [loadRecommendations, loadRuns]);

  const runAnalysis = useCallback(
    async (symbol: string = activeSymbol) => {
      setAnalyzing(true);
      try {
        const result = await api.getAIRecommendation(symbol);
        if (mounted.current) {
          setLatest(result);
          toast.success(`${symbol} → ${result.decision} (${result.confidence.toFixed(0)}% conf.)`);
        }
      } catch (err) {
        if (mounted.current && !(err instanceof ApiError && err.status === 401)) {
          const msg = err instanceof ApiError ? err.detail : 'Analysis failed';
          toast.error(msg);
        }
      } finally {
        if (mounted.current) setAnalyzing(false);
      }
    },
    [activeSymbol],
  );

  const runBacktest = useCallback(async () => {
    const balance = parseNumber(btBalance);
    const risk = parseNumber(btRisk);
    const symbol = btSymbol.trim().toUpperCase();
    if (!symbol) {
      setBtError('Symbol is required');
      return;
    }
    if (balance === null || balance <= 0) {
      setBtError('Initial balance must be a positive number');
      return;
    }
    if (risk === null || risk < 0 || risk > 100) {
      setBtError('Risk % must be between 0 and 100');
      return;
    }
    setBtError(null);
    setBtRunning(true);
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 180);
    try {
      const result = await api.runBacktest({
        symbol,
        timeframe: btTimeframe,
        start_date: start.toISOString(),
        end_date: end.toISOString(),
        initial_balance: balance,
        risk_percentage: risk,
      });
      if (mounted.current) {
        setLastBacktest(result);
        toast.success(`Backtest complete: ${result.total_trades} trades, ${result.win_rate.toFixed(1)}% win`);
      }
      await loadRuns();
    } catch (err) {
      if (mounted.current) {
        const msg = err instanceof ApiError ? err.detail : 'Backtest failed';
        setBtError(msg);
        if (!(err instanceof ApiError && err.status === 401)) toast.error(msg);
      }
    } finally {
      if (mounted.current) setBtRunning(false);
    }
  }, [btSymbol, btTimeframe, btBalance, btRisk, loadRuns]);

  return (
    <div className="min-h-screen bg-forex-bg flex" data-testid="signal-dashboard">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 p-4 md:p-6 overflow-auto">
          <div className="flex flex-wrap items-center gap-2 mb-4 fade-in">
            <span className="glass-panel px-3 py-1.5 rounded-lg text-xs font-mono font-semibold text-forex-bullish border-forex-bullish/30">
              {activeSymbol}
            </span>
            <span className="glass-panel px-3 py-1.5 rounded-lg text-[11px] text-forex-text-muted">
              Signal Dashboard · AI Advisory — no automated trading
            </span>
          </div>

          {/* Latest live analysis banner */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
            <div className="xl:col-span-2 min-h-[220px]">
              <WidgetCard
                title="Latest AI Signal"
                subtitle={latest ? `Analyzed ${formatDateTime(latest.created_at)}` : 'Run a fresh analysis on the active symbol'}
                testId="latest-signal"
                right={
                  <button
                    onClick={() => runAnalysis(activeSymbol)}
                    disabled={analyzing}
                    className="shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-forex-bullish/15 text-forex-bullish border border-forex-bullish/30 hover:bg-forex-bullish/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {analyzing ? 'Analyzing…' : `Analyze ${activeSymbol}`}
                  </button>
                }
              >
                {analyzing && !latest ? (
                  <WidgetSkeleton rows={4} tall />
                ) : latest ? (
                  <div className="h-full flex flex-col gap-3">
                    <div className="rounded-xl border p-4 text-center bg-white/[0.02]">
                      <div className="text-[10px] uppercase tracking-widest text-forex-text-muted mb-1">
                        {latest.symbol} · {latest.market_bias} · {latest.risk_level} risk
                      </div>
                      <div className={cn('text-4xl font-extrabold tracking-tight', DECISION_STYLES[latest.decision]?.text ?? DECISION_STYLES.WAIT.text)}>
                        {latest.decision}
                      </div>
                      <div className="mt-2 flex items-center justify-center gap-2">
                        <div className="flex-1 max-w-[220px]">
                          <MiniBar value={latest.confidence} max={100} />
                        </div>
                        <span className="text-xs font-mono font-semibold text-forex-text">{latest.confidence.toFixed(0)}% conf.</span>
                      </div>
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-center">
                      {[
                        { label: 'Entry', value: latest.entry_price !== null ? formatPrice(latest.entry_price) : '—' },
                        { label: 'Stop Loss', value: latest.stop_loss !== null ? formatPrice(latest.stop_loss) : '—' },
                        { label: 'RR (TP1)', value: latest.risk_reward_ratio !== null ? `1:${latest.risk_reward_ratio}` : '—' },
                        { label: 'Trend', value: latest.trend },
                      ].map((cell) => (
                        <div key={cell.label} className="rounded-lg bg-white/[0.03] border border-white/5 px-2 py-2">
                          <div className="text-[10px] text-forex-text-muted uppercase tracking-wide">{cell.label}</div>
                          <div className="text-xs font-mono font-medium text-forex-text mt-0.5 truncate">{cell.value}</div>
                        </div>
                      ))}
                    </div>
                    <div className="rounded-lg bg-white/[0.02] border border-white/5 p-3">
                      <div className="text-[10px] uppercase tracking-widest text-forex-text-muted mb-1">Reasoning</div>
                      <p className="text-xs leading-relaxed text-forex-text-dim whitespace-pre-wrap max-h-24 overflow-auto">
                        {latest.reasoning}
                      </p>
                    </div>
                  </div>
                ) : (
                  <ErrorState message="No signal yet — run an analysis to see the AI recommendation here." />
                )}
              </WidgetCard>
            </div>

            {/* Run backtest form */}
            <div className="min-h-[220px]">
              <WidgetCard title="Run Backtest" subtitle="Simulate the strategy on historical data" testId="run-backtest">
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <label className="block">
                      <span className="text-[10px] text-forex-text-muted uppercase">Symbol</span>
                      <input
                        value={btSymbol}
                        onChange={(e) => setBtSymbol(e.target.value.toUpperCase() as SymbolCode)}
                        className="glass-input w-full mt-1"
                        placeholder="EURUSD"
                      />
                    </label>
                    <label className="block">
                      <span className="text-[10px] text-forex-text-muted uppercase">Timeframe</span>
                      <select value={btTimeframe} onChange={(e) => setBtTimeframe(e.target.value)} className="glass-input w-full mt-1">
                        {['M15', 'M30', 'H1', 'H4', 'D1'].map((tf) => (
                          <option key={tf} value={tf}>{tf}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <label className="block">
                      <span className="text-[10px] text-forex-text-muted uppercase">Balance ($)</span>
                      <input value={btBalance} onChange={(e) => setBtBalance(e.target.value)} className="glass-input w-full mt-1" inputMode="decimal" />
                    </label>
                    <label className="block">
                      <span className="text-[10px] text-forex-text-muted uppercase">Risk %</span>
                      <input value={btRisk} onChange={(e) => setBtRisk(e.target.value)} className="glass-input w-full mt-1" inputMode="decimal" />
                    </label>
                  </div>
                  {btError && (
                    <div className="p-2 rounded-md bg-forex-bearish-dim border border-forex-bearish/30 text-forex-bearish text-xs">{btError}</div>
                  )}
                  <button
                    onClick={runBacktest}
                    disabled={btRunning}
                    className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {btRunning ? (
                      <>
                        <span className="w-4 h-4 border-2 border-gray-900/30 border-t-gray-900 rounded-full animate-spin" />
                        Running…
                      </>
                    ) : (
                      'Run Backtest'
                    )}
                  </button>
                  {lastBacktest && (
                    <div className="rounded-lg bg-forex-bullish/10 border border-forex-bullish/25 p-2 text-[11px] font-mono">
                      {lastBacktest.symbol}/{lastBacktest.timeframe} — {lastBacktest.total_trades} trades · {lastBacktest.win_rate.toFixed(1)}% win · {'$'}
                      {lastBacktest.final_balance.toFixed(2)} final
                    </div>
                  )}
                </div>
              </WidgetCard>
            </div>
          </div>

          {/* Signals table (persisted AI recommendations) */}
          <div className="mb-4 min-h-[320px]">
            <WidgetCard
              title="AI Signals"
              subtitle="Recent BUY/SELL/WAIT recommendations from the AI decision engine"
              testId="ai-signals"
              right={
                <button
                  onClick={loadRecommendations}
                  className="shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-white/5 text-forex-text border border-forex-border-light hover:bg-white/10 transition-all"
                >
                  ↻ Refresh
                </button>
              }
            >
              {recLoading ? (
                <WidgetSkeleton rows={5} />
              ) : recError ? (
                <ErrorState message={recError} onRetry={loadRecommendations} />
              ) : recommendations.length === 0 ? (
                <EmptyState message="No AI signals yet. Run an analysis on the active symbol to generate the first recommendation." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-forex-text-muted uppercase text-[10px] tracking-widest border-b border-white/5">
                        <th className="py-2 pr-3">Signal</th>
                        <th className="py-2 pr-3">Decision</th>
                        <th className="py-2 pr-3">Confidence</th>
                        <th className="py-2 pr-3">Risk</th>
                        <th className="py-2 pr-3">Trend</th>
                        <th className="py-2 pr-3">Timestamp</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recommendations.map((r) => (
                        <tr key={r.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]" data-testid="signal-row">
                          <td className="py-2.5 pr-3 font-mono font-semibold">{r.symbol}</td>
                          <td className="py-2.5 pr-3">
                            <span className={cn('inline-block px-2 py-0.5 rounded-md text-[10px] font-bold border', DECISION_STYLES[r.decision]?.badge ?? DECISION_STYLES.WAIT.badge)}>
                              {r.decision}
                            </span>
                          </td>
                          <td className="py-2.5 pr-3">
                            <div className="flex items-center gap-2">
                              <div className="w-16"><MiniBar value={r.confidence} max={100} /></div>
                              <span className="font-mono">{r.confidence.toFixed(0)}%</span>
                            </div>
                          </td>
                          <td className="py-2.5 pr-3">{r.risk_level}</td>
                          <td className="py-2.5 pr-3">{r.trend}</td>
                          <td className="py-2.5 pr-3 text-forex-text-muted">{formatDateTime(r.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </WidgetCard>
          </div>

          {/* Backtest runs */}
          <div className="mb-4 min-h-[320px]">
            <WidgetCard
              title="Backtest Runs"
              subtitle="Historical strategy performance — advisory only"
              testId="backtest-runs"
              right={
                <button
                  onClick={loadRuns}
                  className="shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-white/5 text-forex-text border border-forex-border-light hover:bg-white/10 transition-all"
                >
                  ↻ Refresh
                </button>
              }
            >
              {runsLoading ? (
                <WidgetSkeleton rows={5} />
              ) : runsError ? (
                <ErrorState message={runsError} onRetry={loadRuns} />
              ) : runs.length === 0 ? (
                <EmptyState message="No backtests yet. Run a backtest above to see historical strategy performance." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-forex-text-muted uppercase text-[10px] tracking-widest border-b border-white/5">
                        <th className="py-2 pr-3">Market</th>
                        <th className="py-2 pr-3">Outcome</th>
                        <th className="py-2 pr-3">Win Rate</th>
                        <th className="py-2 pr-3">Profit Factor</th>
                        <th className="py-2 pr-3">Max DD</th>
                        <th className="py-2 pr-3">Net</th>
                        <th className="py-2 pr-3">Trades</th>
                        <th className="py-2 pr-3">Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((b) => {
                        const profitable = b.final_balance >= b.initial_balance;
                        return (
                          <tr key={b.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]" data-testid="backtest-row">
                            <td className="py-2.5 pr-3 font-mono font-semibold">{b.symbol}</td>
                            <td className="py-2.5 pr-3">
                              <span
                                className={cn(
                                  'inline-block px-2 py-0.5 rounded-md text-[10px] font-bold border',
                                  profitable
                                    ? 'bg-forex-bullish/15 text-forex-bullish border-forex-bullish/40'
                                    : 'bg-forex-bearish/15 text-forex-bearish border-forex-bearish/40',
                                )}
                              >
                                {profitable ? 'PASS' : 'FAIL'}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 font-mono">{b.win_rate.toFixed(1)}%</td>
                            <td className="py-2.5 pr-3 font-mono">{b.profit_factor !== null ? b.profit_factor.toFixed(2) : '—'}</td>
                            <td className="py-2.5 pr-3 font-mono">{b.max_drawdown.toFixed(2)}%</td>
                            <td className={cn('py-2.5 pr-3 font-mono', profitable ? 'text-forex-bullish' : 'text-forex-bearish')}>
                              {formatPercent(((b.final_balance - b.initial_balance) / b.initial_balance) * 100)}
                            </td>
                            <td className="py-2.5 pr-3">{b.total_trades}</td>
                            <td className="py-2.5 pr-3 text-forex-text-muted">{formatDateTime(b.created_at)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </WidgetCard>
          </div>

          <div className="mt-6 pt-4 border-t border-forex-border flex items-center justify-between text-xs text-forex-text-muted">
            <span>ForexAI Terminal v0.1.0 — Advisory Only</span>
            <span className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-forex-bullish animate-pulse" />
              System Online
            </span>
          </div>
        </main>
      </div>
    </div>
  );
}
