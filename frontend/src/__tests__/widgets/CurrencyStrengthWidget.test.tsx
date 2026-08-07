import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import CurrencyStrengthWidget from '@/components/widgets/CurrencyStrengthWidget';
import { renderWithDashboard } from '@/test/utils';
import { api, type IndicatorResponse } from '@/lib/api';
import { SUPPORTED_SYMBOLS } from '@/contexts/DashboardContext';

vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.status = status;
      this.detail = detail;
      this.name = 'ApiError';
    }
  },
  api: {
    register: vi.fn(),
    login: vi.fn(),
    forgotPassword: vi.fn(),
    refreshToken: vi.fn(),
    getMe: vi.fn(),
    updateSettings: vi.fn(),
    logout: vi.fn(),
    getSymbols: vi.fn(),
    getPrice: vi.fn(),
    getCandles: vi.fn(),
    getMarketStatus: vi.fn(),
    getIndicators: vi.fn(),
    getLatestIndicator: vi.fn(),
    getAIRecommendation: vi.fn(),
    getAIRecommendations: vi.fn(),
    calculateRisk: vi.fn(),
    getPipValues: vi.fn(),
    getBacktestRuns: vi.fn(),
    getBacktestRun: vi.fn(),
  },
}));

function makeIndicator(symbol: string, rsi: number | null): IndicatorResponse {
  return {
    symbol,
    timeframe: 'H1',
    timestamp: new Date().toISOString(),
    ema_20: null,
    ema_50: null,
    ema_200: null,
    supertrend_direction: null,
    supertrend_value: null,
    adx: null,
    rsi,
    macd_line: null,
    macd_signal: null,
    macd_histogram: null,
    stoch_k: null,
    stoch_d: null,
    atr: null,
    bb_upper: null,
    bb_middle: null,
    bb_lower: null,
    vwap: null,
    support_levels: null,
    resistance_levels: null,
    swing_high: null,
    swing_low: null,
    fib_236: null,
    fib_382: null,
    fib_500: null,
    fib_618: null,
    fib_786: null,
  };
}

describe('CurrencyStrengthWidget', () => {
  it('renders every symbol with its RSI-derived strength', async () => {
    vi.mocked(api.getLatestIndicator).mockImplementation((symbol: string) =>
      Promise.resolve({ indicator: makeIndicator(symbol, symbol === 'EURUSD' ? 62 : 48) }),
    );
    renderWithDashboard(<CurrencyStrengthWidget />);

    // Strongest (EURUSD at 62 -> +12.0) is listed first; all names render.
    expect(await screen.findByText('EUR/USD')).toBeInTheDocument();
    expect(screen.getByText('GBP/USD')).toBeInTheDocument();
    expect(screen.getByText('USD/JPY')).toBeInTheDocument();
    // Strength value text: rsi + signed strength
    expect(screen.getByText('62.0 · +12.0')).toBeInTheDocument();
    // Legend
    expect(screen.getByText('Strong')).toBeInTheDocument();
    expect(screen.getByText('Weak')).toBeInTheDocument();
  });

  it('shows an em dash when RSI is unavailable but keeps the row', async () => {
    vi.mocked(api.getLatestIndicator).mockResolvedValue({ indicator: makeIndicator('EURUSD', null) });
    renderWithDashboard(<CurrencyStrengthWidget />);
    expect(await screen.findByText('EUR/USD')).toBeInTheDocument();
    // All 10 rows render a dash instead of a strength value.
    expect(screen.getAllByText('—').length).toBe(SUPPORTED_SYMBOLS.length);
  });

  it('shows the loading skeleton initially', () => {
    vi.mocked(api.getLatestIndicator).mockImplementation(() => new Promise(() => {}));
    renderWithDashboard(<CurrencyStrengthWidget />);
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
  });

  it('shows the error state when the indicator fetch throws synchronously', async () => {
    // Promise.allSettled swallows per-symbol rejections, but a synchronous
    // throw from the loader itself surfaces as the widget error state.
    vi.mocked(api.getLatestIndicator).mockImplementation(() => {
      throw new Error('boom');
    });
    renderWithDashboard(<CurrencyStrengthWidget />);
    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
  });
});
