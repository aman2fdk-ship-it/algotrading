import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LivePricesWidget from '@/components/widgets/LivePricesWidget';
import { renderWithDashboard } from '@/test/utils';
import { api, ApiError, type SymbolResponse, type PriceResponse, type CandleListResponse } from '@/lib/api';
import { DashboardProvider, useDashboard, SUPPORTED_SYMBOLS } from '@/contexts/DashboardContext';

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

const symbols: SymbolResponse[] = SUPPORTED_SYMBOLS.map((code, i) => ({
  code,
  name: `${code.slice(0, 3)}/${code.slice(3)}`,
  asset_type: 'forex',
  pip_size: 0.0001,
  digits: 5,
  enabled: true,
  ...(i === 0 ? { name: 'EUR/USD' } : {}),
}));

function priceFor(code: string, bid: number): PriceResponse {
  return { symbol: code, bid, ask: bid + 0.0002, spread: 2, timestamp: new Date().toISOString() };
}

function candlesFor(code: string, closes: number[]): CandleListResponse {
  return {
    symbol: code,
    timeframe: 'H1',
    count: closes.length,
    candles: closes.map((close) => ({
      symbol: code,
      timeframe: 'H1',
      timestamp: new Date().toISOString(),
      open: close - 0.001,
      high: close + 0.001,
      low: close - 0.002,
      close,
      tick_volume: 100,
      real_volume: 0,
      spread: 2,
    })),
  };
}

function mockMarketData() {
  vi.mocked(api.getSymbols).mockResolvedValue({ symbols, count: symbols.length });
  vi.mocked(api.getPrice).mockImplementation((code: string) =>
    Promise.resolve(priceFor(code, code === 'EURUSD' ? 1.2345 : 0.95)),
  );
  vi.mocked(api.getCandles).mockImplementation((code: string) =>
    Promise.resolve(candlesFor(code, code === 'EURUSD' ? [1.23, 1.24] : [0.95, 0.96])),
  );
}

describe('LivePricesWidget', () => {
  it('renders symbol names and formatted prices once data loads', async () => {
    mockMarketData();
    renderWithDashboard(<LivePricesWidget />);

    expect((await screen.findAllByText('EUR/USD')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('GBP/USD').length).toBeGreaterThan(0);
    // EURUSD bid formatted to 5 digits
    expect(screen.getByText('1.23450')).toBeInTheDocument();
    // H1 change computed from the mocked candles (+0.81%)
    expect(screen.getByText('+0.8%')).toBeInTheDocument();
  });

  it('shows the loading skeleton before the first data arrives', () => {
    vi.mocked(api.getSymbols).mockImplementation(() => new Promise(() => {}));
    renderWithDashboard(<LivePricesWidget />);
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
  });

  it('shows the error state when symbols cannot be loaded', async () => {
    vi.mocked(api.getSymbols).mockRejectedValue(new ApiError(500, 'Market feed down'));
    renderWithDashboard(<LivePricesWidget />);
    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('Market feed down')).toBeInTheDocument();
  });

  it('updates the active symbol when a row is clicked', async () => {
    mockMarketData();
    function ActiveSymbolProbe() {
      const { activeSymbol } = useDashboard();
      return <div data-testid="active-symbol">{activeSymbol}</div>;
    }
    const user = userEvent.setup();
    render(
      <DashboardProvider>
        <ActiveSymbolProbe />
        <LivePricesWidget />
      </DashboardProvider>,
    );

    const row = await screen.findByTitle('Select GBP/USD');
    await user.click(row);
    expect(screen.getByTestId('active-symbol')).toHaveTextContent('GBPUSD');
  });
});
