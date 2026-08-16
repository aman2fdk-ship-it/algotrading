import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import FibonacciWidget from '@/components/widgets/FibonacciWidget';
import { renderWithDashboard } from '@/test/utils';
import {
  api,
  ApiError,
  type FibonacciResponse,
  type SupportResistanceResponse,
} from '@/lib/api';
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
    getTicks: vi.fn(),
    getSmcOrderBlocks: vi.fn(),
    getSmcLiquidity: vi.fn(),
    getSmcFvg: vi.fn(),
    getSupportResistance: vi.fn(),
    getFibonacci: vi.fn(),
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
function makeFibonacci(): FibonacciResponse {
  return {
    symbol: 'EURUSD',
    timeframe: 'H1',
    timestamp: '2026-08-16T00:51:36.797Z',
    fib_0: 0.0,
    fib_236: 1.08498,
    fib_382: 1.08499,
    fib_500: 1.085,
    fib_618: 1.08501,
    fib_786: 1.08502,
    fib_1: 0.0,
  };
}
function makeSr(): SupportResistanceResponse {
  return {
    symbol: 'EURUSD',
    timeframe: 'H1',
    timestamp: '2026-08-16T00:51:36.797Z',
    support_levels: [1.08497],
    resistance_levels: [1.08502],
  };
}
describe('FibonacciWidget', () => {
  it('renders retracement levels and support/resistance from the backend', async () => {
    vi.mocked(api.getFibonacci).mockResolvedValue(makeFibonacci());
    vi.mocked(api.getSupportResistance).mockResolvedValue(makeSr());
    renderWithDashboard(<FibonacciWidget />);
    expect(await screen.findByText('23.6%')).toBeInTheDocument();
    expect(screen.getByText('78.6%')).toBeInTheDocument();
    expect(screen.getByText('1.08498')).toBeInTheDocument();
    expect(screen.getByText('1.08502')).toBeInTheDocument();
    // Support / Resistance chips
    expect(screen.getByText('S 1.08497')).toBeInTheDocument();
    expect(screen.getByText('R 1.08502')).toBeInTheDocument();
    // Backend fib_0/fib_1 are 0.0 placeholders — never rendered as levels.
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
    expect(screen.queryByText('100.0%')).not.toBeInTheDocument();
  });
  it('renders a graceful empty state when the indicator has no data yet (404)', async () => {
    // PR #11 contract: a valid symbol/timeframe with no rows must render an
    // empty state, not an error. The fibonacci/S-R endpoints 404 in that case.
    vi.mocked(api.getFibonacci).mockRejectedValue(new ApiError(404, 'No indicator data found for EURUSD/H1.'));
    vi.mocked(api.getSupportResistance).mockRejectedValue(new ApiError(404, 'No indicator data found for EURUSD/H1.'));
    renderWithDashboard(<FibonacciWidget />);
    expect(await screen.findByText(/No Fibonacci or support\/resistance data for EUR\/USD H1 yet/)).toBeInTheDocument();
    expect(screen.queryByTestId('error-state')).not.toBeInTheDocument();
  });
  it('shows the error state when the backend is down', async () => {
    vi.mocked(api.getFibonacci).mockRejectedValue(new ApiError(503, 'Indicator feed down'));
    vi.mocked(api.getSupportResistance).mockRejectedValue(new ApiError(503, 'Indicator feed down'));
    renderWithDashboard(<FibonacciWidget />);
    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('Indicator feed down')).toBeInTheDocument();
  });
  it('renders support/resistance even when fibonacci has no data yet', async () => {
    vi.mocked(api.getFibonacci).mockRejectedValue(new ApiError(404, 'No indicator data found for EURUSD/H1.'));
    vi.mocked(api.getSupportResistance).mockResolvedValue(makeSr());
    renderWithDashboard(<FibonacciWidget />);
    expect(await screen.findByText('S 1.08497')).toBeInTheDocument();
    expect(screen.getByText(/Fibonacci levels not computed/)).toBeInTheDocument();
    expect(screen.queryByTestId('error-state')).not.toBeInTheDocument();
  });
});
