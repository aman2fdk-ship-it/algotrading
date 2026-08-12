import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChartWidget from '@/components/widgets/ChartWidget';
import { renderWithDashboard } from '@/test/utils';

/**
 * ChartWidget loads the TradingView library from a remote script. In jsdom the
 * script never loads on its own, so tests drive the resolution through
 * window.TradingView and script load/error events on the injected <script>.
 * The module keeps a scriptPromise across mounts, so tests are ordered:
 * loading -> successful widget -> script failure -> retry recovery.
 */

const widgetFactory = vi.fn(() => ({ remove: vi.fn() }));

function stubTradingView() {
  (window as unknown as { TradingView?: unknown }).TradingView = { widget: widgetFactory };
}

function unstubTradingView() {
  delete (window as unknown as { TradingView?: unknown }).TradingView;
}

function tvScriptElement(): HTMLScriptElement | null {
  return document.getElementById('tradingview-tv-js') as HTMLScriptElement | null;
}

beforeEach(() => {
  widgetFactory.mockClear();
  unstubTradingView();
});

afterEach(() => {
  unstubTradingView();
});

describe('ChartWidget', () => {
  it('renders the chart container and timeframe tabs', () => {
    renderWithDashboard(<ChartWidget />);
    expect(screen.getByText('TradingView Chart')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'H1' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'D1' })).toBeInTheDocument();
    expect(document.getElementById('tradingview_chart')).toBeInTheDocument();
  });

  it('shows the loading skeleton while the widget initializes', () => {
    renderWithDashboard(<ChartWidget />);
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
  });

  it('creates a TradingView widget mapped to the active symbol/timeframe', async () => {
    stubTradingView();
    renderWithDashboard(<ChartWidget />);

    await waitFor(() => expect(widgetFactory).toHaveBeenCalled());
    const config = (widgetFactory.mock.calls[0] as any)[0] as { symbol: string; interval: string; theme: string; studies: string[] };
    expect(config.symbol).toBe('OANDA:EURUSD');
    expect(config.interval).toBe('60');
    expect(config.theme).toBe('dark');
    expect(config.studies).toContain('STD;RSI');
  });

  it('rebuilds the widget when the timeframe tab changes', async () => {
    stubTradingView();
    const user = userEvent.setup();
    renderWithDashboard(<ChartWidget />);

    await waitFor(() => expect(widgetFactory).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole('tab', { name: 'M15' }));
    await waitFor(() => expect(widgetFactory).toHaveBeenCalledTimes(2));
    const config = (widgetFactory.mock.calls[1] as any)[0] as { symbol: string; interval: string };
    expect(config.interval).toBe('15');
  });

  it('shows the fallback state when the TradingView script fails to load', async () => {
    // First mount: the script-load promise starts pending (no TradingView global).
    renderWithDashboard(<ChartWidget />);
    // Fail the script load by firing an error on the injected script element.
    await act(async () => {
      tvScriptElement()?.dispatchEvent(new Event('error'));
    });
    expect(await screen.findByText(/Live chart unavailable/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry load' })).toBeInTheDocument();
  });

  it('recovers via Retry load after a script failure', async () => {
    // Trigger the failed-script state again.
    renderWithDashboard(<ChartWidget />);
    await act(async () => {
      tvScriptElement()?.dispatchEvent(new Event('error'));
    });
    await screen.findByText(/Live chart unavailable/);

    // Retry now that the TradingView global is available.
    stubTradingView();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Retry load' }));

    await waitFor(() => expect(widgetFactory).toHaveBeenCalled());
    expect(screen.queryByText(/Live chart unavailable/)).not.toBeInTheDocument();
  });
});
