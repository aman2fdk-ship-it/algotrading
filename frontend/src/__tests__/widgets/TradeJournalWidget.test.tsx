import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TradeJournalWidget from '@/components/widgets/TradeJournalWidget';
import { renderWithDashboard } from '@/test/utils';
import { api } from '@/lib/api';

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

const STORAGE_KEY = 'forexai_trade_journal';

async function addEntry(overrides: { entry?: string; exit?: string; notes?: string } = {}) {
  const user = userEvent.setup();
  const entry = overrides.entry ?? '1.0850';
  const exit = overrides.exit ?? '1.0900';
  await user.type(screen.getByPlaceholderText('1.0850'), entry);
  await user.type(screen.getByPlaceholderText('1.0900'), exit);
  if (overrides.notes) {
    await user.type(screen.getByPlaceholderText('What happened? What did you learn?'), overrides.notes);
  }
  await user.click(screen.getByRole('button', { name: '+ Add Entry' }));
  return user;
}

describe('TradeJournalWidget', () => {
  beforeEach(() => {
    // The widget awaits getPipValues on mount; always provide a settled promise.
    vi.mocked(api.getPipValues).mockResolvedValue({ symbols: [], count: 0 });
  });

  it('renders the form fields', () => {
    renderWithDashboard(<TradeJournalWidget />);
    expect(screen.getByText('Symbol')).toBeInTheDocument();
    expect(screen.getByText('Direction')).toBeInTheDocument();
    expect(screen.getByText('Entry Price')).toBeInTheDocument();
    expect(screen.getByText('Exit Price')).toBeInTheDocument();
    expect(screen.getByText('Emotion')).toBeInTheDocument();
    expect(screen.getByText('Notes')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ Add Entry' })).toBeInTheDocument();
    expect(screen.getByText('BUY')).toHaveClass('bg-forex-bullish/15');
    expect(screen.getByText(/No journal entries yet/)).toBeInTheDocument();
  });

  it('adds an entry, persists it to localStorage and updates totals', async () => {
    vi.mocked(api.getPipValues).mockRejectedValue(new Error('offline')); // falls back to static pip values
    renderWithDashboard(<TradeJournalWidget />);

    await addEntry({ notes: 'Great setup' });

    expect(screen.getByText('EUR/USD')).toBeInTheDocument();
    expect(screen.getByText('Great setup')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument(); // Trades total
    expect(screen.getByText('100%')).toBeInTheDocument(); // Win rate

    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as Array<Record<string, unknown>>;
    expect(stored).toHaveLength(1);
    expect(stored[0]).toMatchObject({ symbol: 'EURUSD', direction: 'BUY', notes: 'Great setup' });
  });

  it('validates entry prices before saving', async () => {
    renderWithDashboard(<TradeJournalWidget />);
    await userEvent.click(screen.getByRole('button', { name: '+ Add Entry' }));
    expect(screen.getByText('Enter a valid entry price')).toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('deletes an entry', async () => {
    renderWithDashboard(<TradeJournalWidget />);
    await addEntry();

    expect(screen.getByText('EUR/USD')).toBeInTheDocument();
    await userEvent.click(screen.getByTitle('Delete entry'));
    expect(screen.queryByText('EUR/USD')).not.toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument(); // Trades back to 0
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')).toHaveLength(0);
  });

  it('loads persisted entries on mount', () => {
    const persisted = [
      {
        id: 'x1',
        symbol: 'GBPUSD',
        direction: 'SELL',
        entryPrice: 1.3,
        exitPrice: 1.29,
        notes: 'Old trade',
        emotion: 'Confident',
        pnlPips: 10,
        pnlUsd: 100,
        createdAt: '2026-07-01T00:00:00.000Z',
      },
    ];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));

    renderWithDashboard(<TradeJournalWidget />);
    expect(screen.getByText('GBP/USD')).toBeInTheDocument();
    expect(screen.getByText('Old trade')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });
});
