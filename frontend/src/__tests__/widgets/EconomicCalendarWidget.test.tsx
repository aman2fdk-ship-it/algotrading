import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import EconomicCalendarWidget from '@/components/widgets/EconomicCalendarWidget';

describe('EconomicCalendarWidget', () => {
  it('renders the calendar title and table headers', () => {
    render(<EconomicCalendarWidget />);
    expect(screen.getByText('Economic Calendar')).toBeInTheDocument();
    expect(screen.getByText('Date')).toBeInTheDocument();
    expect(screen.getByText('Event')).toBeInTheDocument();
    expect(screen.getByText('Currency')).toBeInTheDocument();
    expect(screen.getByText('Forecast')).toBeInTheDocument();
    expect(screen.getByText('Previous')).toBeInTheDocument();
    expect(screen.getByText('Impact')).toBeInTheDocument();
  });

  it('renders the demo events with currencies and impact levels', () => {
    render(<EconomicCalendarWidget />);

    // A sample of the demo events across currencies and impact levels.
    expect(screen.getByText('US GDP (QoQ)')).toBeInTheDocument();
    expect(screen.getByText('FOMC Interest Rate Decision')).toBeInTheDocument();
    expect(screen.getByText('Japan Tokyo CPI (YoY)')).toBeInTheDocument();
    expect(screen.getByText('UK CPI (YoY)')).toBeInTheDocument();
    expect(screen.getByText('Germany IFO Business Climate')).toBeInTheDocument();

    // Currency badges (USD and EUR appear on multiple events).
    expect(screen.getAllByText('USD').length).toBe(3);
    expect(screen.getAllByText('EUR').length).toBe(2);
    expect(screen.getAllByText('JPY').length).toBe(1);
    expect(screen.getAllByText('GBP').length).toBe(1);
    expect(screen.getAllByText('CAD').length).toBe(1);

    // Impact levels.
    expect(screen.getAllByText('High').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Medium').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Low').length).toBeGreaterThan(0);

    // Today's events are labelled "Today, <Mon DD>".
    expect(screen.getAllByText(/^Today,/).length).toBeGreaterThan(0);

    // Forecast / previous values.
    expect(screen.getByText('2.5%')).toBeInTheDocument();
    expect(screen.getByText('3.1%')).toBeInTheDocument();

    // Demo-data disclaimer.
    expect(screen.getByText(/Demo events for illustration/)).toBeInTheDocument();
  });
});
