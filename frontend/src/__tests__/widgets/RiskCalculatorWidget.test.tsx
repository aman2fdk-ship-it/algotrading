import { describe, expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RiskCalculatorWidget from '@/components/widgets/RiskCalculatorWidget';
import { renderWithDashboard } from '@/test/utils';
import { api, ApiError, type RiskCalculateResponse } from '@/lib/api';

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

const riskResult: RiskCalculateResponse = {
  symbol: 'EURUSD',
  account_balance: 10000,
  risk_percentage: 1,
  entry_price: 1.085,
  stop_loss: 1.08,
  leverage: 100,
  position_size: 20000,
  risk_amount: 100,
  stop_loss_pips: 50,
  lot_size: 0.2,
  mini_lots: 2,
  micro_lots: 0,
  required_margin: 217,
  take_profit_1: 1.09,
  take_profit_2: null,
  potential_profit_tp1: 100,
  potential_profit_tp2: null,
  risk_reward_ratio_tp1: 1,
  risk_reward_ratio_tp2: null,
  pip_size: 0.0001,
  pip_value: 10,
};

async function fillPrices() {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText('1.0850'), '1.0850');
  await user.type(screen.getByPlaceholderText('1.0800'), '1.0800');
  return user;
}

describe('RiskCalculatorWidget', () => {
  it('renders all form fields and the calculate button', () => {
    renderWithDashboard(<RiskCalculatorWidget />);
    expect(screen.getByText('Account Balance ($)')).toBeInTheDocument();
    expect(screen.getByText('Risk %')).toBeInTheDocument();
    expect(screen.getByText('Entry Price')).toBeInTheDocument();
    expect(screen.getByText('Stop Loss')).toBeInTheDocument();
    expect(screen.getByText('Symbol')).toBeInTheDocument();
    expect(screen.getByText('Leverage')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Calculate Position' })).toBeInTheDocument();
    // Pre-filled defaults
    expect(screen.getByPlaceholderText('10000')).toHaveValue(10000);
    expect(screen.getByPlaceholderText('100')).toHaveValue(100);
  });

  it('calculates position size on input (debounced) and renders result cards', async () => {
    vi.mocked(api.calculateRisk).mockResolvedValue(riskResult);
    renderWithDashboard(<RiskCalculatorWidget />);

    await fillPrices();

    // Debounce is 450ms; the result should appear shortly after typing stops.
    expect(await screen.findByText('Position Size (units)')).toBeInTheDocument();
    expect(screen.getByText('20,000')).toBeInTheDocument();
    expect(screen.getByText('Risk Amount')).toBeInTheDocument();
    expect(screen.getAllByText('$100.00').length).toBeGreaterThan(0); // Risk Amount + TP1 Profit
    expect(screen.getByText('Stop Loss (pips)')).toBeInTheDocument();
    expect(screen.getByText('R/R TP1')).toBeInTheDocument();

    expect(vi.mocked(api.calculateRisk)).toHaveBeenCalledWith({
      account_balance: 10000,
      risk_percentage: 1,
      entry_price: 1.085,
      stop_loss: 1.08,
      symbol: 'EURUSD',
      leverage: 100,
    });
  });

  it('shows a validation error and then recovers once fields are filled', async () => {
    vi.mocked(api.calculateRisk).mockResolvedValue(riskResult);
    renderWithDashboard(<RiskCalculatorWidget />);

    // Clear the balance to force a validation error.
    await userEvent.clear(screen.getByPlaceholderText('10000'));
    await userEvent.click(screen.getByRole('button', { name: 'Calculate Position' }));
    expect(screen.getByText('Account balance is required')).toBeInTheDocument();

    // Fill everything in and re-calculate.
    await userEvent.type(screen.getByPlaceholderText('10000'), '5000');
    const user = await fillPrices();
    await user.click(screen.getByRole('button', { name: 'Calculate Position' }));

    expect(await screen.findByText('Position Size (units)')).toBeInTheDocument();
    expect(screen.queryByText('Account balance is required')).not.toBeInTheDocument();
  });

  it('shows the loading skeleton while a calculation is in flight', async () => {
    vi.mocked(api.calculateRisk).mockImplementation(() => new Promise(() => {}));
    renderWithDashboard(<RiskCalculatorWidget />);

    await fillPrices();
    await userEvent.click(screen.getByRole('button', { name: 'Calculate Position' }));
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
  });

  it('surfaces backend errors inline', async () => {
    vi.mocked(api.calculateRisk).mockRejectedValue(new ApiError(400, 'Stop loss must be below entry'));
    renderWithDashboard(<RiskCalculatorWidget />);

    await fillPrices();
    await userEvent.click(screen.getByRole('button', { name: 'Calculate Position' }));
    expect(await screen.findByText('Stop loss must be below entry')).toBeInTheDocument();
  });
});
