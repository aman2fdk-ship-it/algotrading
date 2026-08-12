import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  cn,
  WidgetCard,
  Skeleton,
  WidgetSkeleton,
  ErrorState,
  EmptyState,
  Sparkline,
  MiniBar,
  StatRow,
  cssVars,
} from '@/components/widgets/shared';
import { formatSymbolLabel } from '@/components/widgets/LivePricesWidget';

describe('cn', () => {
  it('joins truthy parts and skips falsy ones', () => {
    expect(cn('a', 'b', false, null, undefined, 'c')).toBe('a b c');
  });
});

describe('WidgetCard', () => {
  it('renders title, subtitle, right slot and children', () => {
    render(
      <WidgetCard title="My Card" subtitle="a subtitle" right={<button>Go</button>} testId="card">
        <p>body content</p>
      </WidgetCard>,
    );
    expect(screen.getByText('My Card')).toBeInTheDocument();
    expect(screen.getByText('a subtitle')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Go' })).toBeInTheDocument();
    expect(screen.getByText('body content')).toBeInTheDocument();
    expect(screen.getByTestId('card')).toBeInTheDocument();
  });

  it('omits the subtitle when not provided', () => {
    render(<WidgetCard title="Only Title">x</WidgetCard>);
    expect(screen.getByText('Only Title')).toBeInTheDocument();
  });
});

describe('Skeleton', () => {
  it('renders a skeleton block', () => {
    render(<Skeleton className="h-8" />);
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
  });
});

describe('WidgetSkeleton', () => {
  it('renders the given number of rows with a Loading label', () => {
    render(<WidgetSkeleton rows={4} />);
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
    expect(document.querySelectorAll('.animate-pulse')).toHaveLength(4);
  });

  it('defaults to 4 rows', () => {
    render(<WidgetSkeleton />);
    expect(document.querySelectorAll('.animate-pulse')).toHaveLength(4);
  });
});

describe('ErrorState', () => {
  it('renders the message', () => {
    render(<ErrorState message="Something broke" />);
    expect(screen.getByText('Something broke')).toBeInTheDocument();
    expect(screen.getByTestId('error-state')).toBeInTheDocument();
  });

  it('fires onRetry when the Retry button is clicked', async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<ErrorState message="Boom" onRetry={onRetry} />);
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('renders no button without onRetry', () => {
    render(<ErrorState message="Boom" />);
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });
});

describe('EmptyState', () => {
  it('renders the message', () => {
    render(<EmptyState message="Nothing here yet" />);
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument();
  });
});

describe('Sparkline', () => {
  it('shows a message when there is not enough data', () => {
    render(<Sparkline data={[1]} />);
    expect(screen.getByText('Not enough data')).toBeInTheDocument();
  });

  it('renders an svg polyline for 2+ points', () => {
    render(<Sparkline data={[1, 2, 3]} />);
    expect(document.querySelector('svg polyline')).toBeInTheDocument();
    expect(document.querySelector('svg polygon')).toBeInTheDocument();
  });
});

describe('MiniBar', () => {
  it('exposes progressbar semantics with clamped values', () => {
    render(<MiniBar value={200} max={100} min={0} />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '100');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
  });

  it('clamps low values up to the min', () => {
    render(<MiniBar value={-5} max={100} min={0} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  });
});

describe('StatRow', () => {
  it('renders label and value', () => {
    render(<StatRow label="Expectancy" value="$12.00" />);
    expect(screen.getByText('Expectancy')).toBeInTheDocument();
    expect(screen.getByText('$12.00')).toBeInTheDocument();
  });
});

describe('cssVars', () => {
  it('passes through a record of CSS custom properties', () => {
    const vars = cssVars({ '--w': '50%' });
    expect((vars as Record<string, string>)['--w']).toBe('50%');
  });
});

describe('formatSymbolLabel', () => {
  it('inserts a slash in 6-character codes', () => {
    expect(formatSymbolLabel('EURUSD')).toBe('EUR/USD');
    expect(formatSymbolLabel('BTCUSD')).toBe('BTC/USD');
  });

  it('returns non-6-char codes unchanged', () => {
    expect(formatSymbolLabel('GOLD')).toBe('GOLD');
  });
});
