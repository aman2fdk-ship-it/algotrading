import { useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type PipValueItem } from '@/lib/api';
import { SUPPORTED_SYMBOLS } from '@/contexts/DashboardContext';
import { WidgetCard, cn } from './shared';
import { formatCurrency, formatDateTime, parseNumber, sanitizeInputNumber } from '@/lib/format';
import { formatSymbolLabel } from './LivePricesWidget';

const STORAGE_KEY = 'forexai_trade_journal';
const EMOTIONS = ['Confident', 'Disciplined', 'Nervous', 'Impulsive', 'Fearful', 'Greedy'] as const;
type Emotion = (typeof EMOTIONS)[number];

interface JournalEntry {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  entryPrice: number;
  exitPrice: number;
  notes: string;
  emotion: Emotion;
  pnlPips: number;
  pnlUsd: number;
  createdAt: string;
}

const FALLBACK_PIP_VALUES: Record<string, number> = {
  EURUSD: 10,
  GBPUSD: 10,
  USDJPY: 9.07,
  AUDUSD: 10,
  NZDUSD: 10,
  USDCAD: 7.4,
  USDCHF: 10.5,
  XAUUSD: 10,
  BTCUSD: 10,
  ETHUSD: 10,
};

function loadEntries(): JournalEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as JournalEntry[]) : [];
  } catch {
    return [];
  }
}

function computePnl(
  symbol: string,
  direction: 'BUY' | 'SELL',
  entry: number,
  exit: number,
  pipValues: Map<string, number>,
): { pips: number; usd: number } {
  const pipValue = pipValues.get(symbol) ?? FALLBACK_PIP_VALUES[symbol] ?? 10;
  const rawPips = (exit - entry) / pipValue;
  const pips = direction === 'BUY' ? rawPips : -rawPips;
  return { pips, usd: pips * pipValue };
}

export default function TradeJournalWidget() {
  const [entries, setEntries] = useState<JournalEntry[]>(() => loadEntries());
  const [symbol, setSymbol] = useState('EURUSD');
  const [direction, setDirection] = useState<'BUY' | 'SELL'>('BUY');
  const [entryPrice, setEntryPrice] = useState('');
  const [exitPrice, setExitPrice] = useState('');
  const [notes, setNotes] = useState('');
  const [emotion, setEmotion] = useState<Emotion>('Confident');
  const [pipValues, setPipValues] = useState<Map<string, number>>(new Map());
  const [formError, setFormError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  // Load pip values once for P&L estimation.
  useEffect(() => {
    let cancelled = false;
    api
      .getPipValues()
      .then((res: { symbols: PipValueItem[] }) => {
        if (cancelled) return;
        setPipValues(new Map(res.symbols.map((s) => [s.symbol, s.pip_value_per_lot])));
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) return;
        // Non-fatal — fallback pip values are used.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const persist = (next: JournalEntry[]) => {
    setEntries(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      toast.error('Could not save journal — localStorage full?');
    }
  };

  const addEntry = () => {
    const entry = parseNumber(entryPrice);
    const exit = parseNumber(exitPrice);
    if (entry === null || entry <= 0) {
      setFormError('Enter a valid entry price');
      return;
    }
    if (exit === null || exit <= 0) {
      setFormError('Enter a valid exit price');
      return;
    }
    const { pips, usd } = computePnl(symbol, direction, entry, exit, pipValues);
    const entryRecord: JournalEntry = {
      id: crypto.randomUUID(),
      symbol,
      direction,
      entryPrice: entry,
      exitPrice: exit,
      notes: notes.trim(),
      emotion,
      pnlPips: pips,
      pnlUsd: usd,
      createdAt: new Date().toISOString(),
    };
    persist([entryRecord, ...entries]);
    setEntryPrice('');
    setExitPrice('');
    setNotes('');
    setFormError(null);
    toast.success(`Journal entry saved (${pips >= 0 ? '+' : ''}${pips.toFixed(1)} pips)`);
  };

  const removeEntry = (id: string) => {
    persist(entries.filter((e) => e.id !== id));
  };

  const totals = useMemo(() => {
    const pips = entries.reduce((acc, e) => acc + e.pnlPips, 0);
    const usd = entries.reduce((acc, e) => acc + e.pnlUsd, 0);
    const wins = entries.filter((e) => e.pnlUsd > 0).length;
    return { pips, usd, count: entries.length, wins };
  }, [entries]);

  const inputClass = 'glass-input !py-2 !px-3 text-xs font-mono';

  return (
    <WidgetCard
      title="Trade Journal"
      subtitle="Local journal — stored in your browser (server sync is a future enhancement)"
      testId="trade-journal"
    >
      <div className="h-full flex flex-col lg:flex-row gap-4 overflow-auto">
        {/* Form */}
        <div className="lg:w-1/3 shrink-0 space-y-2.5">
          <div className="grid grid-cols-2 gap-2.5">
            <label className="block">
              <span className="text-[10px] text-forex-text-muted mb-1 block">Symbol</span>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className={cn(inputClass, 'appearance-none')}
              >
                {SUPPORTED_SYMBOLS.map((s) => (
                  <option key={s} value={s} className="bg-forex-surface text-forex-text">
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] text-forex-text-muted mb-1 block">Direction</span>
              <div className="grid grid-cols-2 gap-1">
                {(['BUY', 'SELL'] as const).map((dir) => (
                  <button
                    key={dir}
                    type="button"
                    onClick={() => setDirection(dir)}
                    className={cn(
                      'py-2 rounded-md text-[11px] font-bold border transition-all',
                      direction === dir
                        ? dir === 'BUY'
                          ? 'bg-forex-bullish/15 text-forex-bullish border-forex-bullish/40'
                          : 'bg-forex-bearish/15 text-forex-bearish border-forex-bearish/40'
                        : 'bg-white/[0.02] text-forex-text-muted border-white/10 hover:bg-white/5',
                    )}
                  >
                    {dir}
                  </button>
                ))}
              </div>
            </label>
            <label className="block">
              <span className="text-[10px] text-forex-text-muted mb-1 block">Entry Price</span>
              <input
                type="number"
                step="any"
                value={entryPrice}
                onChange={(e) => setEntryPrice(sanitizeInputNumber(e.target.value))}
                className={inputClass}
                placeholder="1.0850"
              />
            </label>
            <label className="block">
              <span className="text-[10px] text-forex-text-muted mb-1 block">Exit Price</span>
              <input
                type="number"
                step="any"
                value={exitPrice}
                onChange={(e) => setExitPrice(sanitizeInputNumber(e.target.value))}
                className={inputClass}
                placeholder="1.0900"
              />
            </label>
            <label className="block col-span-2">
              <span className="text-[10px] text-forex-text-muted mb-1 block">Emotion</span>
              <select
                value={emotion}
                onChange={(e) => setEmotion(e.target.value as Emotion)}
                className={cn(inputClass, 'appearance-none')}
              >
                {EMOTIONS.map((em) => (
                  <option key={em} value={em} className="bg-forex-surface text-forex-text">
                    {em}
                  </option>
                ))}
              </select>
            </label>
            <label className="block col-span-2">
              <span className="text-[10px] text-forex-text-muted mb-1 block">Notes</span>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                className={cn(inputClass, 'resize-none')}
                placeholder="What happened? What did you learn?"
              />
            </label>
          </div>

          {formError && (
            <div className="rounded-lg bg-forex-bearish/10 border border-forex-bearish/25 px-3 py-2 text-[11px] text-forex-bearish">
              {formError}
            </div>
          )}

          <button onClick={addEntry} className="btn-primary !py-2 text-xs w-full">
            + Add Entry
          </button>

          {/* Running P&L */}
          <div className="grid grid-cols-3 gap-2 pt-1">
            <div className="rounded-lg bg-white/[0.03] border border-white/5 px-2 py-1.5 text-center">
              <div className="text-[9px] uppercase text-forex-text-muted">Trades</div>
              <div className="text-sm font-mono font-semibold text-forex-text">{totals.count}</div>
            </div>
            <div className="rounded-lg bg-white/[0.03] border border-white/5 px-2 py-1.5 text-center">
              <div className="text-[9px] uppercase text-forex-text-muted">Win rate</div>
              <div className="text-sm font-mono font-semibold text-forex-text">
                {totals.count > 0 ? `${((totals.wins / totals.count) * 100).toFixed(0)}%` : '—'}
              </div>
            </div>
            <div className="rounded-lg bg-white/[0.03] border border-white/5 px-2 py-1.5 text-center">
              <div className="text-[9px] uppercase text-forex-text-muted">P&L</div>
              <div className={cn('text-sm font-mono font-semibold', totals.usd >= 0 ? 'text-forex-bullish' : 'text-forex-bearish')}>
                {formatCurrency(totals.usd)}
              </div>
            </div>
          </div>
          <p className="text-[10px] text-forex-text-muted">
            P&L estimated at 1 standard lot using live pip values · {totals.pips >= 0 ? '+' : ''}
            {totals.pips.toFixed(1)} pips total
          </p>
        </div>

        {/* Entry list */}
        <div className="lg:flex-1 min-w-0">
          <div ref={listRef} className="h-full overflow-auto pr-1 space-y-1.5">
            {entries.length === 0 ? (
              <div className="h-full flex items-center justify-center text-center">
                <p className="text-xs text-forex-text-muted max-w-[260px]">
                  No journal entries yet. Log your first trade above — entries are saved in this browser.
                </p>
              </div>
            ) : (
              entries.map((e) => {
                const win = e.pnlUsd >= 0;
                return (
                  <div
                    key={e.id}
                    className={cn(
                      'rounded-lg border px-3 py-2',
                      win ? 'border-forex-bullish/15 bg-forex-bullish/[0.04]' : 'border-forex-bearish/15 bg-forex-bearish/[0.04]',
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-semibold text-forex-text">{formatSymbolLabel(e.symbol)}</span>
                      <span
                        className={cn(
                          'px-1.5 py-0.5 rounded text-[9px] font-bold border',
                          e.direction === 'BUY'
                            ? 'bg-forex-bullish/15 text-forex-bullish border-forex-bullish/40'
                            : 'bg-forex-bearish/15 text-forex-bearish border-forex-bearish/40',
                        )}
                      >
                        {e.direction}
                      </span>
                      <span className="text-[10px] text-forex-text-muted">{e.emotion}</span>
                      <span className="text-[10px] text-forex-text-muted ml-auto">{formatDateTime(e.createdAt)}</span>
                      <button
                        onClick={() => removeEntry(e.id)}
                        title="Delete entry"
                        className="text-forex-text-muted hover:text-forex-bearish transition-colors text-xs px-1"
                      >
                        ✕
                      </button>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[10px] font-mono text-forex-text-muted">
                      <span>
                        {e.entryPrice.toFixed(5)} → {e.exitPrice.toFixed(5)}
                      </span>
                      <span className={win ? 'text-forex-bullish' : 'text-forex-bearish'}>
                        {e.pnlPips >= 0 ? '+' : ''}
                        {e.pnlPips.toFixed(1)} pips · {formatCurrency(e.pnlUsd)}
                      </span>
                    </div>
                    {e.notes && <p className="text-[11px] text-forex-text-dim mt-1">{e.notes}</p>}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </WidgetCard>
  );
}
