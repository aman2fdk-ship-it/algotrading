import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import SMCWidget from '@/components/widgets/SMCWidget';
import { renderWithDashboard } from '@/test/utils';
import {
  api,
  ApiError,
  type SMCOrderBlockResponse,
  type SMCLiquidityResponse,
  type SMCFVGResponse,
  type SMCStructureResponse,
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
function makeStructure(overrides: Partial<SMCStructureResponse> = {}): SMCStructureResponse {
  return {
    id: 'uuid-1',
    symbol: 'EURUSD',
    timeframe: 'H1',
    timestamp: '2026-08-16T01:51:52.035Z',
    structure_type: 'fvg',
    direction: 'bearish',
    price_low: 1.08499,
    price_high: 1.085,
    price_mid: 1.08499,
    key_level: null,
    confidence: 0.47,
    details: null,
    created_at: '2026-08-16T01:51:52.035Z',
    ...overrides,
  };
}
function emptyOrderBlocks(): SMCOrderBlockResponse {
  return { order_blocks: [], symbol: 'EURUSD', timeframe: 'H1', count: 0 };
}
function emptyLiquidity(): SMCLiquidityResponse {
  return { liquidity_sweeps: [], symbol: 'EURUSD', timeframe: 'H1', count: 0 };
}
function emptyFvg(): SMCFVGResponse {
  return { fair_value_gaps: [], symbol: 'EURUSD', timeframe: 'H1', count: 0 };
}
describe('SMCWidget', () => {
  it('renders order blocks, liquidity sweeps and FVGs with levels and confidence', async () => {
    vi.mocked(api.getSmcOrderBlocks).mockResolvedValue({
      order_blocks: [makeStructure({ id: 'ob-1', structure_type: 'order_block', direction: 'bullish', price_low: 1.083, price_high: 1.0832, confidence: 0.8 })],
      symbol: 'EURUSD',
      timeframe: 'H1',
      count: 1,
    });
    vi.mocked(api.getSmcLiquidity).mockResolvedValue({
      liquidity_sweeps: [makeStructure({ id: 'liq-1', structure_type: 'liquidity_sweep', direction: 'bearish', key_level: 1.086, confidence: 0.65 })],
      symbol: 'EURUSD',
      timeframe: 'H1',
      count: 1,
    });
    vi.mocked(api.getSmcFvg).mockResolvedValue({
      fair_value_gaps: [makeStructure({ id: 'fvg-1', structure_type: 'fvg', direction: 'bearish', price_low: 1.08499, price_high: 1.085, confidence: 0.47 })],
      symbol: 'EURUSD',
      timeframe: 'H1',
      count: 1,
    });
    renderWithDashboard(<SMCWidget />);
    expect(await screen.findByText('Order Blocks')).toBeInTheDocument();
    expect(screen.getByText('Liquidity Sweeps')).toBeInTheDocument();
    expect(screen.getByText('Fair Value Gaps')).toBeInTheDocument();
    // Order block level range
    expect(screen.getByText('1.08300 – 1.08320')).toBeInTheDocument();
    // Liquidity sweep key level
    expect(screen.getByText('1.08600')).toBeInTheDocument();
    // Direction badges
    expect(screen.getAllByText('bullish').length).toBeGreaterThan(0);
    expect(screen.getAllByText('bearish').length).toBeGreaterThan(0);
    // Confidence percentages (formatPercent adds a leading '+' for positive values)
    expect(screen.getByText('+80%')).toBeInTheDocument();
    expect(screen.getByText('+47%')).toBeInTheDocument();
  });
  it('renders a graceful empty state when no structures exist for the symbol/timeframe', async () => {
    vi.mocked(api.getSmcOrderBlocks).mockResolvedValue(emptyOrderBlocks());
    vi.mocked(api.getSmcLiquidity).mockResolvedValue(emptyLiquidity());
    vi.mocked(api.getSmcFvg).mockResolvedValue(emptyFvg());
    renderWithDashboard(<SMCWidget />);
    expect(await screen.findByText(/No SMC structures detected for EUR\/USD H1 yet/)).toBeInTheDocument();
    expect(screen.queryByTestId('error-state')).not.toBeInTheDocument();
  });
  it('shows the error state when every SMC source fails', async () => {
    vi.mocked(api.getSmcOrderBlocks).mockRejectedValue(new ApiError(503, 'SMC feed down'));
    vi.mocked(api.getSmcLiquidity).mockRejectedValue(new ApiError(503, 'SMC feed down'));
    vi.mocked(api.getSmcFvg).mockRejectedValue(new ApiError(503, 'SMC feed down'));
    renderWithDashboard(<SMCWidget />);
    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('SMC feed down')).toBeInTheDocument();
  });
  it('renders available sections even when one source fails', async () => {
    vi.mocked(api.getSmcOrderBlocks).mockResolvedValue({
      order_blocks: [makeStructure({ id: 'ob-1', structure_type: 'order_block', direction: 'bullish', price_low: 1.083, price_high: 1.0832, confidence: 0.8 })],
      symbol: 'EURUSD',
      timeframe: 'H1',
      count: 1,
    });
    vi.mocked(api.getSmcLiquidity).mockRejectedValue(new ApiError(503, 'liquidity down'));
    vi.mocked(api.getSmcFvg).mockResolvedValue(emptyFvg());
    renderWithDashboard(<SMCWidget />);
    expect(await screen.findByText('Order Blocks')).toBeInTheDocument();
    expect(screen.getByText('1.08300 – 1.08320')).toBeInTheDocument();
    expect(screen.getByText('Liquidity Sweeps')).toBeInTheDocument();
    expect(screen.getByText(/Unavailable/)).toBeInTheDocument();
  });
});
