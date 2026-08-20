/** Formatting + parsing helpers shared across dashboard widgets. */

/** Format a price with the number of digits typical for the symbol. */
export function formatPrice(value: number, digits = 5): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Format a decimal quantity (position size, lots). */
export function formatQuantity(value: number, digits = 2): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Format a percent. */
export function formatPercent(value: number, digits = 1): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

/** Format a currency amount. */
export function formatCurrency(value: number, digits = 2): string {
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${sign}$${abs}`;
}

/** Short ISO date-time for tables (e.g. 2026-07-20 14:32). */
export function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
/** Time-only format for tick tables (e.g. 14:32:05). Returns '—' for invalid input. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** Parse a numeric string, returning null when invalid/empty. */
export function parseNumber(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === '') return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Strip a leading '+' from a form value so Number() accepts it. */
export function sanitizeInputNumber(value: string): string {
  return value.trim().replace(/^\+/, '');
}
