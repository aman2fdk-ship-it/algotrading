import {
  createContext,
  useContext,
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export const SUPPORTED_SYMBOLS = [
  'EURUSD',
  'GBPUSD',
  'USDJPY',
  'AUDUSD',
  'NZDUSD',
  'USDCAD',
  'USDCHF',
  'XAUUSD',
  'BTCUSD',
  'ETHUSD',
] as const;

export type SymbolCode = (typeof SUPPORTED_SYMBOLS)[number];

export const SUPPORTED_TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'] as const;

export type Timeframe = (typeof SUPPORTED_TIMEFRAMES)[number];

export const isSupportedSymbol = (value: string): value is SymbolCode =>
  (SUPPORTED_SYMBOLS as readonly string[]).includes(value);

interface DashboardState {
  activeSymbol: SymbolCode;
  activeTimeframe: Timeframe;
  setActiveSymbol: (symbol: string) => void;
  setActiveTimeframe: (timeframe: string) => void;
}

const DashboardContext = createContext<DashboardState | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [activeSymbol, setActiveSymbolState] = useState<SymbolCode>('EURUSD');
  const [activeTimeframe, setActiveTimeframeState] = useState<Timeframe>('H1');

  const setActiveSymbol = useCallback((symbol: string) => {
    const normalized = symbol.toUpperCase();
    setActiveSymbolState((prev) => {
      if (prev === normalized && isSupportedSymbol(normalized)) return prev;
      return isSupportedSymbol(normalized) ? normalized : prev;
    });
  }, []);

  const setActiveTimeframe = useCallback((timeframe: string) => {
    const normalized = timeframe.toUpperCase();
    setActiveTimeframeState((prev) => {
      if (prev === normalized && (SUPPORTED_TIMEFRAMES as readonly string[]).includes(normalized)) {
        return prev;
      }
      return (SUPPORTED_TIMEFRAMES as readonly string[]).includes(normalized)
        ? (normalized as Timeframe)
        : prev;
    });
  }, []);

  const value = useMemo<DashboardState>(
    () => ({ activeSymbol, activeTimeframe, setActiveSymbol, setActiveTimeframe }),
    [activeSymbol, activeTimeframe, setActiveSymbol, setActiveTimeframe],
  );

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard(): DashboardState {
  const ctx = useContext(DashboardContext);
  if (!ctx) {
    throw new Error('useDashboard must be used within DashboardProvider');
  }
  return ctx;
}
