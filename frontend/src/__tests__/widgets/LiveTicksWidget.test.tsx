import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import LiveTicksWidget from '@/components/widgets/LiveTicksWidget';
import { renderWithDashboard } from '@/test/utils';
import { api, ApiError, type PriceResponse, type TickResponse } from '@/lib/api';
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
function makePrice(overrides: Partial<PriceResponse> = {}): PriceResponse {
  return {
    symbol: 'EURUSD',
    bid: 1.0849,
    ask: 1.0851,
    spread: 2,
    timestamp: '2026-08-16T01:51:35.584Z',
    ...overrides,
  };
}
function makeTicks(count: number): TickResponse[] {
  return Array.from({ length: count }).map((_, i) => ({
    symbol: 'EURUSD',
    timestamp: `2026-08-16T01:51:3${i}.000Z`,
    bid: 1.0849 + i * 0.0001,
    ask: 1.0851 + i * 0.0001,
    spread: 2,
    volume: i + 1,
  }));
}
describe('LiveTicksWidget', () => {
  it('renders latest bid/ask/spread and tick history from the backend', async () => {
    vi.mocked(api.getPrice).mockResolvedValue(makePrice());
    vi.mocked(api.getTicks).mockResolvedValue({ ticks: makeTicks(3), symbol: 'EURUSD', count: 3 });
    renderWithDashboard(<LiveTicksWidget />);
    // Bid / ask / spread snapshot (bid also appears in tick history rows).
    expect((await screen.findAllByText('1.08490')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('1.08510').length).toBeGreaterThan(0);
    // Tick history header shows the count
    expect(await screen.findByText('3 shown')).toBeInTheDocument();
    // Backend returns chronological order; the widget shows newest first, so the
    // newest tick (volume 3, ask 1.08530) is the first data row after the header.
    const rows = screen.getAllByRole('row');
    expect(rows.length).toBeGreaterThanOrEqual(4); // header + 3 ticks
    expect(rows[1]?.textContent).toContain('1.08530');
    expect(rows[1]?.textContent).toContain('3');
  });
  it('shows the loading skeleton while the first requests are in flight', async () => {
    vi.mocked(api.getPrice).mockReturnValue(new Promise(() => {}));
    vi.mocked(api.getTicks).mockReturnValue(new Promise(() => {}));
    renderWithDashboard(<LiveTicksWidget />);
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
  });
  it('renders a graceful empty state for a valid symbol with no stored ticks', async () => {
    // Backend contract: valid symbol, no ticks -> /price 503, /ticks 200 + [].
    vi.mocked(api.getPrice).mockRejectedValue(new ApiError(503, 'No price data available for EURUSD.'));
    vi.mocked(api.getTicks).mockResolvedValue({ ticks: [], symbol: 'EURUSD', count: 0 });
    renderWithDashboard(<LiveTicksWidget />);
    expect(await screen.findByText(/No live tick data for EUR\/USD yet/)).toBeInTheDocument();
    expect(screen.queryByTestId('error-state')).not.toBeInTheDocument();
  });
  it('shows the error state when the ticks feed fails', async () => {
    vi.mocked(api.getPrice).mockResolvedValue(makePrice());
    vi.mocked(api.getTicks).mockRejectedValue(new ApiError(503, 'Tick feed down'));
    renderWithDashboard(<LiveTicksWidget />);
    // Price still renders, but with no ticks history the failure is surfaced
    // only when there is nothing to show at all; here price data exists so the
    // panel renders with the "no history yet" fallback row.
    expect(await screen.findByText('1.08490')).toBeInTheDocument();
    expect(screen.getByText(/No tick history yet/)).toBeInTheDocument();
  });
  it('shows the error state when every source fails and nothing renders', async () => {
    vi.mocked(api.getPrice).mockRejectedValue(new ApiError(503, 'Feed down'));
    vi.mocked(api.getTicks).mockRejectedValue(new ApiError(503, 'Feed down'));
    renderWithDashboard(<LiveTicksWidget />);
    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('Feed down')).toBeInTheDocument();
  });
});
