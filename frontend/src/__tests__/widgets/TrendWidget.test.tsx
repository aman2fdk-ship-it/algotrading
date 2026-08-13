import { describe, expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import TrendWidget from '@/components/widgets/TrendWidget';
import { renderWithDashboard } from '@/test/utils';
import { api, ApiError, type IndicatorResponse } from '@/lib/api';

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

function makeIndicator(overrides: Partial<IndicatorResponse> = {}): IndicatorResponse {
  return {
    symbol: 'EURUSD',
    timeframe: 'H1',
    timestamp: new Date().toISOString(),
    ema_20: 1.101,
    ema_50: 1.095,
    ema_200: 1.08,
    supertrend_direction: 1,
    supertrend_value: 1.09,
    adx: 30,
    rsi: 62,
    macd_line: 0.002,
    macd_signal: 0.001,
    macd_histogram: 0.001,
    stoch_k: 70,
    stoch_d: 65,
    atr: 0.005,
    bb_upper: 1.11,
    bb_middle: 1.1,
    bb_lower: 1.09,
    vwap: 1.099,
    support_levels: [1.08],
    resistance_levels: [1.11],
    swing_high: 1.115,
    swing_low: 1.085,
    fib_236: 1.09,
    fib_382: 1.093,
    fib_500: 1.095,
    fib_618: 1.098,
    fib_786: 1.102,
    ...overrides,
  };
}

describe('TrendWidget', () => {
  it('renders a Bullish direction with momentum and key levels', async () => {
    vi.mocked(api.getLatestIndicator).mockResolvedValue({ indicator: makeIndicator() });
    renderWithDashboard(<TrendWidget />);

    expect((await screen.findAllByText('Bullish')).length).toBeGreaterThan(0);
    expect(screen.getByText(/RSI Momentum/)).toBeInTheDocument();
    expect(screen.getByText(/62\.0/)).toBeInTheDocument();
    expect(screen.getByText('EMA alignment')).toBeInTheDocument();
    expect(screen.getByText('ATR (volatility)')).toBeInTheDocument();
  });

  it('renders Bearish when EMAs are stacked down and RSI is weak', async () => {
    vi.mocked(api.getLatestIndicator).mockResolvedValue({
      indicator: makeIndicator({ ema_20: 1.08, ema_50: 1.09, ema_200: 1.1, rsi: 35, supertrend_direction: -1 }),
    });
    renderWithDashboard(<TrendWidget />);
    expect((await screen.findAllByText('Bearish')).length).toBeGreaterThan(0);
  });

  it('renders Neutral for a flat signal', async () => {
    vi.mocked(api.getLatestIndicator).mockResolvedValue({
      // Mixed EMA alignment (1.09 < 1.095 but 1.095 > 1.08), neutral RSI, no supertrend vote.
      indicator: makeIndicator({ ema_20: 1.09, ema_50: 1.095, ema_200: 1.08, rsi: 50, supertrend_direction: null }),
    });
    renderWithDashboard(<TrendWidget />);
    expect(await screen.findByText('Neutral')).toBeInTheDocument();
  });

  it('shows the loading skeleton initially', async () => {
    let resolve!: (v: { indicator: IndicatorResponse }) => void;
    vi.mocked(api.getLatestIndicator).mockReturnValue(
      new Promise<{ indicator: IndicatorResponse }>((res) => {
        resolve = res;
      }),
    );
    renderWithDashboard(<TrendWidget />);
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();

    await act(async () => {
      resolve({ indicator: makeIndicator() });
    });
    expect((await screen.findAllByText('Bullish')).length).toBeGreaterThan(0);
  });

  it('shows the error state when the request fails', async () => {
    vi.mocked(api.getLatestIndicator).mockRejectedValue(new ApiError(503, 'Indicator feed down'));
    renderWithDashboard(<TrendWidget />);
    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('Indicator feed down')).toBeInTheDocument();
  });

  it('shows an empty state when the API returns 200 with a null indicator', async () => {
    // Backend contract: valid symbol+timeframe with no rows -> 200, indicator: null.
    vi.mocked(api.getLatestIndicator).mockResolvedValue({ indicator: null });
    renderWithDashboard(<TrendWidget />);
    expect(
      await screen.findByText(/No indicator data yet/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('error-state')).not.toBeInTheDocument();
  });
});
