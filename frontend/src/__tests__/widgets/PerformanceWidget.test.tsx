import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PerformanceWidget from '@/components/widgets/PerformanceWidget';
import { renderWithDashboard } from '@/test/utils';
import { api, ApiError, type BacktestResultResponse, type BacktestRunSummary } from '@/lib/api';

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

function makeRun(id: string, overrides: Partial<BacktestRunSummary> = {}): BacktestRunSummary {
  return {
    id,
    user_id: 'u1',
    symbol: 'EURUSD',
    timeframe: 'H1',
    start_date: '2026-06-01T00:00:00Z',
    end_date: '2026-07-01T00:00:00Z',
    initial_balance: 10000,
    risk_percentage: 1,
    final_balance: 11200,
    total_trades: 34,
    win_rate: 58.8,
    profit_factor: 1.5,
    max_drawdown: -6.2,
    expectancy: 35.29,
    sharpe_ratio: 1.1,
    created_at: '2026-07-02T00:00:00Z',
    ...overrides,
  };
}

const runDetail: BacktestResultResponse = {
  ...makeRun('r1'),
  avg_win: 120,
  avg_loss: -80,
  largest_win: 400,
  largest_loss: -250,
  avg_hold_time: 4.5,
  equity_curve: [
    { timestamp: '2026-06-01T00:00:00Z', balance: 10000 },
    { timestamp: '2026-07-01T00:00:00Z', balance: 11200 },
  ],
  trades: [
    {
      id: 't1',
      symbol: 'EURUSD',
      timeframe: 'H1',
      direction: 'BUY',
      entry_time: '2026-06-10T00:00:00Z',
      exit_time: '2026-06-10T04:00:00Z',
      entry_price: 1.08,
      exit_price: 1.085,
      position_size: 0.5,
      pnl: 250,
      pnl_pct: 2.5,
      exit_reason: 'TP1',
      created_at: '2026-06-10T04:00:00Z',
    },
  ],
};

describe('PerformanceWidget', () => {
  it('renders backtest run summaries', async () => {
    vi.mocked(api.getBacktestRuns).mockResolvedValue({
      runs: [
        makeRun('r1'),
        makeRun('r2', { symbol: 'GBPUSD', timeframe: 'D1', final_balance: 8000, total_trades: 12, win_rate: 45.0, profit_factor: 0.8 }),
      ],
      count: 2,
    });
    renderWithDashboard(<PerformanceWidget />);

    expect(await screen.findByText('EUR/USD')).toBeInTheDocument();
    expect(screen.getByText('GBP/USD')).toBeInTheDocument();
    expect(screen.getByText('H1')).toBeInTheDocument();
    expect(screen.getByText('D1')).toBeInTheDocument();
    expect(screen.getByText('58.8%')).toBeInTheDocument(); // win rate
    expect(screen.getByText('1.50')).toBeInTheDocument(); // profit factor
    expect(screen.getByText('+12.0%')).toBeInTheDocument(); // net return (11200 vs 10000)
    expect(screen.getByText('34')).toBeInTheDocument(); // trades
  });

  it('expands a run to show detail stats and trades', async () => {
    vi.mocked(api.getBacktestRuns).mockResolvedValue({ runs: [makeRun('r1')], count: 1 });
    vi.mocked(api.getBacktestRun).mockResolvedValue(runDetail);
    const user = userEvent.setup();
    renderWithDashboard(<PerformanceWidget />);

    await screen.findByText('EUR/USD');
    await user.click(screen.getByTitle('Click for full detail'));

    expect(await screen.findByText('Expectancy')).toBeInTheDocument();
    expect(screen.getByText('$35.29')).toBeInTheDocument();
    expect(screen.getByText('Sharpe ratio')).toBeInTheDocument();
    expect(screen.getByText('1.10')).toBeInTheDocument();
    expect(screen.getByText('BUY EUR/USD')).toBeInTheDocument();
    expect(screen.getByText('+$250.00')).toBeInTheDocument();
  });

  it('shows the empty state when there are no runs', async () => {
    vi.mocked(api.getBacktestRuns).mockResolvedValue({ runs: [], count: 0 });
    renderWithDashboard(<PerformanceWidget />);
    expect(await screen.findByText(/No backtest runs yet/)).toBeInTheDocument();
  });

  it('shows the loading skeleton initially', () => {
    vi.mocked(api.getBacktestRuns).mockImplementation(() => new Promise(() => {}));
    renderWithDashboard(<PerformanceWidget />);
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
  });

  it('shows the error state when the fetch fails', async () => {
    vi.mocked(api.getBacktestRuns).mockRejectedValue(new ApiError(500, 'Backtest service unavailable'));
    renderWithDashboard(<PerformanceWidget />);
    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('Backtest service unavailable')).toBeInTheDocument();
  });
});
