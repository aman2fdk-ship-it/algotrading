import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OpenOpportunitiesWidget from '@/components/widgets/OpenOpportunitiesWidget';
import { renderWithDashboard } from '@/test/utils';
import { api, ApiError, type RecommendationResponse } from '@/lib/api';
import { DashboardProvider, useDashboard } from '@/contexts/DashboardContext';

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

function makeRecommendation(id: string, overrides: Partial<RecommendationResponse> = {}): RecommendationResponse {
  return {
    id,
    symbol: 'EURUSD',
    decision: 'BUY',
    confidence: 78,
    entry_price: 1.085,
    stop_loss: 1.08,
    take_profit_1: 1.095,
    take_profit_2: null,
    risk_reward_ratio: 2,
    trend: 'Bullish',
    market_bias: 'Strong',
    risk_level: 'Low',
    reasoning: 'Trend continuation',
    timeframe_scores: { H1: 1 },
    created_at: '2026-08-01T10:00:00Z',
    ...overrides,
  };
}

describe('OpenOpportunitiesWidget', () => {
  it('renders the recommendation list with badges and levels', async () => {
    vi.mocked(api.getAIRecommendations).mockResolvedValue({
      recommendations: [
        makeRecommendation('r1'),
        makeRecommendation('r2', { symbol: 'GBPUSD', decision: 'SELL', confidence: 55, entry_price: 1.3, stop_loss: 1.31, take_profit_1: 1.28 }),
      ],
      count: 2,
    });
    renderWithDashboard(<OpenOpportunitiesWidget />);

    expect(await screen.findByText('EUR/USD')).toBeInTheDocument();
    expect(screen.getByText('GBP/USD')).toBeInTheDocument();
    expect(screen.getByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('SELL')).toBeInTheDocument();
    expect(screen.getByText('78%')).toBeInTheDocument();
    expect(screen.getByText('1.08500')).toBeInTheDocument();
  });

  it('shows the empty state when there are no recommendations', async () => {
    vi.mocked(api.getAIRecommendations).mockResolvedValue({ recommendations: [], count: 0 });
    renderWithDashboard(<OpenOpportunitiesWidget />);
    expect(await screen.findByText(/No AI recommendations yet/)).toBeInTheDocument();
  });

  it('shows the loading skeleton initially', () => {
    vi.mocked(api.getAIRecommendations).mockImplementation(() => new Promise(() => {}));
    renderWithDashboard(<OpenOpportunitiesWidget />);
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
  });

  it('shows the error state when the fetch fails', async () => {
    vi.mocked(api.getAIRecommendations).mockRejectedValue(new ApiError(503, 'AI engine offline'));
    renderWithDashboard(<OpenOpportunitiesWidget />);
    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('AI engine offline')).toBeInTheDocument();
  });

  it('selects the symbol in context when an opportunity is clicked', async () => {
    vi.mocked(api.getAIRecommendations).mockResolvedValue({
      recommendations: [makeRecommendation('r1', { symbol: 'XAUUSD', decision: 'WAIT', confidence: 60 })],
      count: 1,
    });
    function ActiveSymbolProbe() {
      const { activeSymbol } = useDashboard();
      return <div data-testid="active-symbol">{activeSymbol}</div>;
    }
    const user = userEvent.setup();
    render(
      <DashboardProvider>
        <ActiveSymbolProbe />
        <OpenOpportunitiesWidget />
      </DashboardProvider>,
    );

    const row = await screen.findByText('XAU/USD');
    await user.click(row);
    expect(screen.getByTestId('active-symbol')).toHaveTextContent('XAUUSD');
  });
});
