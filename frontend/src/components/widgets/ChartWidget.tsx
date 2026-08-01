import { useEffect, useRef, useState } from 'react';
import { useDashboard, SUPPORTED_TIMEFRAMES, type Timeframe } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, cn } from './shared';
import { formatSymbolLabel } from './LivePricesWidget';

/* TradingView widget global (loaded from the free s3 bundle). */
interface TradingViewWidgetConfig {
  container_id: string;
  symbol: string;
  interval: string;
  theme: 'dark';
  style: '1';
  locale: string;
  autosize: boolean;
  timezone: string;
  hide_side_toolbar: boolean;
  allow_symbol_change: boolean;
  save_image: boolean;
  studies?: string[];
}
interface TradingViewWidgetInstance {
  remove: () => void;
}
declare global {
  interface Window {
    TradingView?: {
      widget: new (config: TradingViewWidgetConfig) => TradingViewWidgetInstance;
    };
  }
}

const TV_SCRIPT_URL = 'https://s3.tradingview.com/tv.js';

/** Map internal timeframes to TradingView intervals. */
const INTERVAL_MAP: Record<Timeframe, string> = {
  M1: '1',
  M5: '5',
  M15: '15',
  M30: '30',
  H1: '60',
  H4: '240',
  D1: 'D',
};

/** Map our symbol codes to TradingView exchange symbols. */
function toTvSymbol(code: string): string {
  if (code === 'BTCUSD') return 'BITSTAMP:BTCUSD';
  if (code === 'ETHUSD') return 'BITSTAMP:ETHUSD';
  if (code === 'XAUUSD') return 'OANDA:XAUUSD';
  if (code === 'USDJPY') return 'OANDA:USDJPY';
  return `OANDA:${code}`;
}

let scriptPromise: Promise<boolean> | null = null;

function loadTvScript(): Promise<boolean> {
  if (window.TradingView) return Promise.resolve(true);
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<boolean>((resolve) => {
    const existing = document.getElementById('tradingview-tv-js');
    if (existing) {
      existing.addEventListener('load', () => resolve(Boolean(window.TradingView)), { once: true });
      existing.addEventListener('error', () => resolve(false), { once: true });
      return;
    }
    const script = document.createElement('script');
    script.id = 'tradingview-tv-js';
    script.src = TV_SCRIPT_URL;
    script.async = true;
    script.onload = () => resolve(Boolean(window.TradingView));
    script.onerror = () => {
      scriptPromise = null; // allow retry later
      resolve(false);
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export default function ChartWidget() {
  const { activeSymbol, activeTimeframe, setActiveTimeframe } = useDashboard();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetRef = useRef<TradingViewWidgetInstance | null>(null);
  const [scriptReady, setScriptReady] = useState(false);
  const [scriptFailed, setScriptFailed] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Load the TradingView script once.
  useEffect(() => {
    let cancelled = false;
    loadTvScript().then((ok) => {
      if (cancelled) return;
      setScriptReady(ok);
      if (!ok) setScriptFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // (Re)create the widget when symbol/timeframe/script changes.
  useEffect(() => {
    if (!scriptReady) return;
    const container = containerRef.current;
    if (!container) return;
    const tv = window.TradingView;
    if (!tv) return;

    // Clear previous instance.
    if (widgetRef.current) {
      try {
        widgetRef.current.remove();
      } catch {
        // ignore — container is being replaced anyway
      }
      widgetRef.current = null;
    }
    container.innerHTML = '';

    setIsLoading(true);
    try {
      widgetRef.current = new tv.widget({
        container_id: 'tradingview_chart',
        symbol: toTvSymbol(activeSymbol),
        interval: INTERVAL_MAP[activeTimeframe],
        theme: 'dark',
        style: '1',
        locale: 'en',
        autosize: true,
        timezone: 'Etc/UTC',
        hide_side_toolbar: false,
        allow_symbol_change: true,
        save_image: true,
        studies: ['STD;RSI'],
      });
    } catch {
      setScriptFailed(true);
    }

    // The widget can't tell us directly when it is ready; a short timeout
    // lets the iframe render before we drop the skeleton.
    const t = window.setTimeout(() => setIsLoading(false), 900);
    return () => {
      window.clearTimeout(t);
      if (widgetRef.current) {
        try {
          widgetRef.current.remove();
        } catch {
          // ignore
        }
        widgetRef.current = null;
      }
    };
  }, [activeSymbol, activeTimeframe, scriptReady]);

  const fallback = scriptFailed;

  return (
    <WidgetCard
      title="TradingView Chart"
      subtitle={`${formatSymbolLabel(activeSymbol)} · ${activeTimeframe}`}
      testId="chart"
      right={
        <div className="flex items-center gap-1 flex-wrap justify-end" role="tablist" aria-label="Timeframe">
          {SUPPORTED_TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              role="tab"
              aria-selected={tf === activeTimeframe}
              onClick={() => setActiveTimeframe(tf)}
              className={cn(
                'px-2 py-1 rounded-md text-[11px] font-medium font-mono transition-all',
                tf === activeTimeframe
                  ? 'bg-forex-bullish/15 text-forex-bullish border border-forex-bullish/30'
                  : 'text-forex-text-muted hover:text-forex-text hover:bg-white/5 border border-transparent',
              )}
            >
              {tf}
            </button>
          ))}
        </div>
      }
    >
      <div className="relative h-full min-h-[380px] w-full rounded-lg overflow-hidden bg-forex-surface/50 border border-forex-border">
        {fallback ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-6">
            <div className="w-14 h-14 rounded-full bg-forex-bullish-dim flex items-center justify-center mb-4">
              <svg className="w-7 h-7 text-forex-bullish" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M7 12l3-3 3 3 4-4M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"
                />
              </svg>
            </div>
            <p className="text-2xl font-semibold font-mono text-forex-text">
              {formatSymbolLabel(activeSymbol)} · {activeTimeframe}
            </p>
            <p className="text-xs text-forex-text-muted mt-2 max-w-[320px]">
              Live chart unavailable — the TradingView library could not be loaded from{' '}
              <span className="font-mono">{TV_SCRIPT_URL}</span>. Check your network connection and retry.
            </p>
            <button
              onClick={() => {
                scriptPromise = null;
                setScriptFailed(false);
                loadTvScript().then((ok) => {
                  setScriptReady(ok);
                  if (!ok) setScriptFailed(true);
                });
              }}
              className="mt-4 px-4 py-1.5 rounded-lg text-xs font-medium bg-white/5 hover:bg-white/10 text-forex-text border border-forex-border-light transition-all"
            >
              Retry load
            </button>
          </div>
        ) : (
          <>
            {isLoading && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-forex-surface/40">
                <WidgetSkeleton rows={6} tall />
              </div>
            )}
            <div id="tradingview_chart" ref={containerRef} className="absolute inset-0" />
          </>
        )}
      </div>
      <p className="text-[10px] text-forex-text-muted mt-2 text-center shrink-0">
        Chart data via TradingView · Advisory only — no automated trading
      </p>
    </WidgetCard>
  );
}
