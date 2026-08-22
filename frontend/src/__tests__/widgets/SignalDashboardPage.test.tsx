import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import SignalDashboardPage from '@/pages/SignalDashboardPage';
import { DashboardProvider } from '@/contexts/DashboardContext';
import { AuthProvider } from '@/contexts/AuthContext';
import { api, ApiError, type RecommendationResponse } from '@/lib/api';

vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...(actual as object), useNavigate: () => vi.fn() };
});
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
    getSymbols: vi.fn().mockResolvedValue({ symbols: [], count: 0 }),
    getAIRecommendations: vi.fn(),
    getBacktestRuns: vi.fn(),
    getAIRecommendation: vi.fn(),
    runBacktest: vi.fn(),
  },
}));

const rec: RecommendationResponse = {
  id: 'r1',
  symbol: 'EURUSD',
  decision: 'BUY',
  confidence: 82,
  entry_price: 1.085,
  stop_loss: 1.08,
  take_profit_1: null,
  take_profit_2: null,
  risk_reward_ratio: 1.5,
  trend: 'Bullish',
  market_bias: 'Buy',
  risk_level: 'Low',
  reasoning: 'strong trend',
  timeframe_scores: {},
  created_at: '2026-08-20T00:00:00Z',
};

const run = {
  id: 'b1',
  user_id: 'u1',
  symbol: 'GBPUSD',
  timeframe: 'H1',
  start_date: '2026-01-01T00:00:00Z',
  end_date: '2026-08-01T00:00:00Z',
  initial_balance: 10000,
  risk_percentage: 1,
  final_balance: 11250,
  total_trades: 20,
  win_rate: 60,
  profit_factor: 1.8,
  max_drawdown: 6.2,
  expectancy: 12.5,
  sharpe_ratio: 1.1,
  created_at: '2026-08-20T00:00:00Z',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <DashboardProvider>
          <Routes>
            <Route path="/" element={<SignalDashboardPage />} />
          </Routes>
        </DashboardProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('SignalDashboardPage', () => {
  it('renders AI signals from the backend with decision badges', async () => {
    vi.mocked(api.getAIRecommendations).mockResolvedValue({ recommendations: [rec], count: 1 });
    vi.mocked(api.getBacktestRuns).mockResolvedValue({ runs: [run], count: 1 });
    renderPage();
    expect(await screen.findByText('EURUSD')).toBeInTheDocument();
    expect(screen.getByTestId('signal-dashboard')).toBeInTheDocument();
  });
  it('renders a graceful empty state when there are no signals', async () => {
    vi.mocked(api.getAIRecommendations).mockResolvedValue({ recommendations: [], count: 0 });
    vi.mocked(api.getBacktestRuns).mockResolvedValue({ runs: [], count: 0 });
    renderPage();
    expect(await screen.findByText(/No AI signals yet/i)).toBeInTheDocument();
    expect(await screen.findByText(/No backtests yet/i)).toBeInTheDocument();
  });
  it('renders an error state with retry when the API fails', async () => {
    vi.mocked(api.getAIRecommendations).mockRejectedValue(new ApiError(503, 'Signals feed down'));
    vi.mocked(api.getBacktestRuns).mockResolvedValue({ runs: [], count: 0 });
    renderPage();
    expect(await screen.findByText('Signals feed down')).toBeInTheDocument();
  });
});
