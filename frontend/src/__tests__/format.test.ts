import { describe, expect, it } from 'vitest';
import {
  formatPrice,
  formatQuantity,
  formatPercent,
  formatCurrency,
  formatDateTime,
  parseNumber,
  sanitizeInputNumber,
} from '@/lib/format';

describe('formatPrice', () => {
  it('formats with 5 digits by default', () => {
    expect(formatPrice(1.23456)).toBe('1.23456');
  });

  it('pads with trailing zeros', () => {
    expect(formatPrice(1.2)).toBe('1.20000');
  });

  it('honours a custom digits count', () => {
    expect(formatPrice(1234.5, 2)).toBe('1,234.50');
  });
});

describe('formatQuantity', () => {
  it('formats with 2 digits by default', () => {
    expect(formatQuantity(1234.5)).toBe('1,234.50');
  });

  it('rounds to the requested digits', () => {
    expect(formatQuantity(0.215, 1)).toBe('0.2');
  });
});

describe('formatPercent', () => {
  it('adds a leading plus for positive values', () => {
    expect(formatPercent(12.345)).toBe('+12.3%');
  });

  it('keeps a minus sign for negative values', () => {
    expect(formatPercent(-4.56)).toBe('-4.6%');
  });

  it('has no sign for zero', () => {
    expect(formatPercent(0)).toBe('0.0%');
  });

  it('honours custom digits', () => {
    expect(formatPercent(1.5, 2)).toBe('+1.50%');
  });
});

describe('formatCurrency', () => {
  it('formats positive amounts with $ and thousands separators', () => {
    expect(formatCurrency(12345.6)).toBe('$12,345.60');
  });

  it('prefixes negative amounts with a minus', () => {
    expect(formatCurrency(-50)).toBe('-$50.00');
  });

  it('honours custom digits', () => {
    expect(formatCurrency(99.999, 0)).toBe('$100');
  });
});

describe('formatDateTime', () => {
  it('formats an ISO string as YYYY-MM-DD HH:mm', () => {
    // Construct a timezone-stable date (UTC-based ISO string).
    const iso = new Date(Date.UTC(2026, 6, 20, 14, 32)).toISOString();
    expect(formatDateTime(iso)).toMatch(/^2026-07-20 \d{2}:32$/);
  });

  it('returns an em dash for null/undefined-ish input', () => {
    expect(formatDateTime(null)).toBe('—');
  });

  it('returns an em dash for invalid dates', () => {
    expect(formatDateTime('not-a-date')).toBe('—');
  });
});

describe('parseNumber', () => {
  it('parses valid numeric strings', () => {
    expect(parseNumber('1.0850')).toBe(1.085);
    expect(parseNumber(' -42 ')).toBe(-42);
  });

  it('returns null for empty strings', () => {
    expect(parseNumber('')).toBeNull();
    expect(parseNumber('   ')).toBeNull();
  });

  it('returns null for non-numeric strings', () => {
    expect(parseNumber('abc')).toBeNull();
    expect(parseNumber('Infinity')).toBeNull();
  });
});

describe('sanitizeInputNumber', () => {
  it('strips a leading plus sign', () => {
    expect(sanitizeInputNumber('+1.5')).toBe('1.5');
  });

  it('trims surrounding whitespace', () => {
    expect(sanitizeInputNumber('  12  ')).toBe('12');
  });

  it('leaves negative numbers untouched', () => {
    expect(sanitizeInputNumber('-3')).toBe('-3');
  });
});
