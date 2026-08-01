import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type RiskCalculateResponse } from '@/lib/api';
import { SUPPORTED_SYMBOLS } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, ErrorState, cn } from './shared';
import { formatCurrency, formatQuantity, parseNumber, sanitizeInputNumber } from '@/lib/format';

interface FormState {
  accountBalance: string;
  riskPercentage: string;
  entryPrice: string;
  stopLoss: string;
  symbol: string;
  leverage: string;
}

const initialForm: FormState = {
  accountBalance: '10000',
  riskPercentage: '1',
  entryPrice: '',
  stopLoss: '',
  symbol: 'EURUSD',
  leverage: '100',
};

export default function RiskCalculatorWidget() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [result, setResult] = useState<RiskCalculateResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const requestIdRef = useRef(0);
  const debounceRef = useRef<number | null>(null);

  const setField = (field: keyof FormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setTouched(true);
  };

  const validate = (f: FormState): string | null => {
    if (parseNumber(f.accountBalance) === null) return 'Account balance is required';
    if (parseNumber(f.riskPercentage) === null) return 'Risk % is required';
    if (parseNumber(f.entryPrice) === null) return 'Entry price is required';
    if (parseNumber(f.stopLoss) === null) return 'Stop loss is required';
    if (f.symbol === '') return 'Select a symbol';
    if (parseNumber(f.leverage) === null) return 'Leverage is required';
    return null;
  };

  const calculate = async (f: FormState) => {
    const invalid = validate(f);
    if (invalid) {
      setError(invalid);
      return;
    }
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.calculateRisk({
        account_balance: parseNumber(f.accountBalance) as number,
        risk_percentage: parseNumber(f.riskPercentage) as number,
        entry_price: parseNumber(f.entryPrice) as number,
        stop_loss: parseNumber(f.stopLoss) as number,
        symbol: f.symbol.toUpperCase(),
        leverage: parseNumber(f.leverage) as number,
      });
      if (requestIdRef.current !== requestId) return;
      setResult(res);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      const message = err instanceof ApiError ? err.detail : 'Calculation failed';
      setError(message);
      if (!(err instanceof ApiError && err.status === 401)) toast.error(message);
    } finally {
      if (requestIdRef.current === requestId) setIsLoading(false);
    }
  };

  // Debounced instant calculation once the user has started typing.
  useEffect(() => {
    if (!touched) return;
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      void calculate(form);
    }, 450);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, touched]);

  useEffect(() => {
    return () => {
      requestIdRef.current += 1;
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, []);

  const inputClass = 'glass-input !py-2 !px-3 text-xs font-mono';

  const statCards: Array<{ label: string; value: string; accent?: boolean }> = result
    ? [
        { label: 'Position Size (units)', value: formatQuantity(result.position_size, 0) },
        { label: 'Lot Size (standard)', value: formatQuantity(result.lot_size, 2) },
        { label: 'Mini / Micro lots', value: `${formatQuantity(result.mini_lots)} / ${formatQuantity(result.micro_lots)}` },
        { label: 'Required Margin', value: formatCurrency(result.required_margin) },
        { label: 'Risk Amount', value: formatCurrency(result.risk_amount), accent: true },
        { label: 'Stop Loss (pips)', value: formatQuantity(result.stop_loss_pips, 1) },
        ...(result.take_profit_1 !== null
          ? [{ label: 'TP1 Profit', value: formatCurrency(result.potential_profit_tp1 ?? 0) }]
          : []),
        ...(result.take_profit_2 !== null
          ? [{ label: 'TP2 Profit', value: formatCurrency(result.potential_profit_tp2 ?? 0) }]
          : []),
      ]
    : [];

  return (
    <WidgetCard
      title="Risk Calculator"
      subtitle="Position size & margin — advisory only"
      testId="risk-calculator"
    >
      <div className="h-full flex flex-col gap-3 overflow-auto">
        <div className="grid grid-cols-2 gap-2.5">
          <label className="block">
            <span className="text-[10px] text-forex-text-muted mb-1 block">Account Balance ($)</span>
            <input
              type="number"
              min="0"
              value={form.accountBalance}
              onChange={(e) => setField('accountBalance', sanitizeInputNumber(e.target.value))}
              className={inputClass}
              placeholder="10000"
            />
          </label>
          <label className="block">
            <span className="text-[10px] text-forex-text-muted mb-1 block">Risk %</span>
            <input
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={form.riskPercentage}
              onChange={(e) => setField('riskPercentage', sanitizeInputNumber(e.target.value))}
              className={inputClass}
              placeholder="1.0"
            />
          </label>
          <label className="block">
            <span className="text-[10px] text-forex-text-muted mb-1 block">Entry Price</span>
            <input
              type="number"
              step="any"
              value={form.entryPrice}
              onChange={(e) => setField('entryPrice', sanitizeInputNumber(e.target.value))}
              className={inputClass}
              placeholder="1.0850"
            />
          </label>
          <label className="block">
            <span className="text-[10px] text-forex-text-muted mb-1 block">Stop Loss</span>
            <input
              type="number"
              step="any"
              value={form.stopLoss}
              onChange={(e) => setField('stopLoss', sanitizeInputNumber(e.target.value))}
              className={inputClass}
              placeholder="1.0800"
            />
          </label>
          <label className="block">
            <span className="text-[10px] text-forex-text-muted mb-1 block">Symbol</span>
            <select
              value={form.symbol}
              onChange={(e) => setField('symbol', e.target.value)}
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
            <span className="text-[10px] text-forex-text-muted mb-1 block">Leverage</span>
            <input
              type="number"
              min="1"
              value={form.leverage}
              onChange={(e) => setField('leverage', sanitizeInputNumber(e.target.value))}
              className={inputClass}
              placeholder="100"
            />
          </label>
        </div>

        <button
          onClick={() => calculate(form)}
          disabled={isLoading}
          className="btn-primary !py-2 text-xs w-full disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Calculating…' : 'Calculate Position'}
        </button>

        {isLoading && !result && <WidgetSkeleton rows={4} />}

        {error && (
          <div className="rounded-lg bg-forex-bearish/10 border border-forex-bearish/25 px-3 py-2 text-[11px] text-forex-bearish">
            {error}
          </div>
        )}

        {result && !isLoading && (
          <div className="grid grid-cols-2 gap-2">
            {statCards.map((card) => (
              <div
                key={card.label}
                className={cn(
                  'rounded-lg border px-2.5 py-2',
                  card.accent ? 'bg-forex-bullish/10 border-forex-bullish/25' : 'bg-white/[0.03] border-white/5',
                )}
              >
                <div className="text-[9px] uppercase tracking-wide text-forex-text-muted">{card.label}</div>
                <div className={cn('text-xs font-mono font-semibold mt-0.5 truncate', card.accent ? 'text-forex-bullish' : 'text-forex-text')}>
                  {card.value}
                </div>
              </div>
            ))}
            {result.risk_reward_ratio_tp1 !== null && (
              <div className="col-span-2 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-2 text-center">
                <span className="text-[10px] text-forex-text-muted">R/R TP1 </span>
                <span className="text-xs font-mono font-semibold text-forex-cyan">{result.risk_reward_ratio_tp1.toFixed(2)}</span>
                {result.risk_reward_ratio_tp2 !== null && (
                  <>
                    <span className="text-[10px] text-forex-text-muted"> · R/R TP2 </span>
                    <span className="text-xs font-mono font-semibold text-forex-cyan">{result.risk_reward_ratio_tp2.toFixed(2)}</span>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </WidgetCard>
  );
}
