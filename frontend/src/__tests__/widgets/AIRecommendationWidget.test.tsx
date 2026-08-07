import { describe, expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AIRecommendationWidget from '@/components/widgets/AIRecommendationWidget';
import { renderWithDashboard } from '@/test/utils';
import { api, ApiError, type DecisionResult } from '@/lib/api';

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

function makeDecision(decision: DecisionResult['decision']): DecisionResult {
  return {
    symbol: 'EURUSD',
    decision,
    confidence: 82,
    entry_price: 1.085,
    stop_loss: 1.08,
    take_profit_1: 1.095,
    take_profit_2: 1.1,
    risk_reward_ratio: 2.5,
    trend: 'Bullish',
    market_bias: 'Strong',
    risk_level: 'Medium',
    reasoning: 'Momentum aligns with the higher-timeframe trend.',
    timeframe_scores: { H1: 1.2 },
    timeframe_details: [{ timeframe: 'H1', score: 1.2, weight: 0.5, category_scores: { trend: 1.2 } }],
    created_at: new Date().toISOString(),
  };
}

describe('AIRecommendationWidget', () => {
  it('renders the BUY badge, confidence and reasoning', async () => {
    vi.mocked(api.getAIRecommendation).mockResolvedValue(makeDecision('BUY'));
    renderWithDashboard(<AIRecommendationWidget />);

    expect(await screen.findByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('82% conf.')).toBeInTheDocument();
    expect(screen.getByText('Momentum aligns with the higher-timeframe trend.')).toBeInTheDocument();
    expect(screen.getByText(/EURUSD/)).toBeInTheDocument();
    // Refresh button enables the user to re-run analysis
    expect(screen.getByRole('button', { name: /Refresh Analysis/ })).toBeInTheDocument();
  });

  it.each(['BUY', 'SELL', 'WAIT'] as const)('renders the %s decision badge', async (decision) => {
    vi.mocked(api.getAIRecommendation).mockResolvedValue(makeDecision(decision));
    renderWithDashboard(<AIRecommendationWidget />);
    expect(await screen.findByText(decision)).toBeInTheDocument();
  });

  it('shows the loading skeleton while the request is in flight', async () => {
    let resolve!: (v: DecisionResult) => void;
    vi.mocked(api.getAIRecommendation).mockReturnValue(
      new Promise<DecisionResult>((res) => {
        resolve = res;
      }),
    );
    renderWithDashboard(<AIRecommendationWidget />);
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();

    await act(async () => {
      resolve(makeDecision('WAIT'));
    });
    expect(await screen.findByText('WAIT')).toBeInTheDocument();
    expect(screen.queryByLabelText('Loading')).not.toBeInTheDocument();
  });

  it('shows the error state and recovers via retry', async () => {
    vi.mocked(api.getAIRecommendation).mockRejectedValue(new ApiError(500, 'Backend unavailable'));
    renderWithDashboard(<AIRecommendationWidget />);

    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('Backend unavailable')).toBeInTheDocument();

    // Retry re-runs the analysis and renders the result.
    vi.mocked(api.getAIRecommendation).mockResolvedValue(makeDecision('SELL'));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('SELL')).toBeInTheDocument();
    expect(screen.queryByTestId('error-state')).not.toBeInTheDocument();
  });
});
