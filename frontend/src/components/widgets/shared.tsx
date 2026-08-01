import type { ReactNode, CSSProperties } from 'react';

/** Tiny className joiner that skips falsy values. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

/** Glassmorphism card with a header row (title + optional right slot). */
export function WidgetCard({
  title,
  subtitle,
  right,
  children,
  className,
  testId,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <div className={cn('glass-panel p-5 h-full flex flex-col fade-in', className)} data-testid={testId}>
      <div className="flex items-start justify-between gap-3 mb-4 shrink-0">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-forex-text truncate">{title}</h3>
          {subtitle && <p className="text-[11px] text-forex-text-muted mt-0.5 truncate">{subtitle}</p>}
        </div>
        {right}
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}

/** Animated skeleton block. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-white/5', className)} />;
}

/** Full-body loading skeleton used by every widget while first data arrives. */
export function WidgetSkeleton({ rows = 4, tall = false }: { rows?: number; tall?: boolean }) {
  return (
    <div className="space-y-3" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn('w-full', tall ? 'h-16' : 'h-8', i % 2 === 0 ? 'bg-white/[0.04]' : 'bg-white/[0.07]')}
        />
      ))}
    </div>
  );
}

/** Inline error state with a retry button. */
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center p-4" data-testid="error-state">
      <svg
        className="w-8 h-8 mb-2 text-forex-bearish/70"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
        />
      </svg>
      <p className="text-xs text-forex-text-dim max-w-[240px] break-words">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 px-4 py-1.5 rounded-lg text-xs font-medium bg-white/5 hover:bg-white/10 text-forex-text border border-forex-border-light transition-all active:scale-[0.98]"
        >
          Retry
        </button>
      )}
    </div>
  );
}

/** Empty state for widgets with no data yet. */
export function EmptyState({ message }: { message: string }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center p-4">
      <p className="text-xs text-forex-text-muted max-w-[260px]">{message}</p>
    </div>
  );
}

/** Simple SVG sparkline used for mini equity curves. */
export function Sparkline({
  data,
  width = 220,
  height = 44,
  color = '#00d4aa',
}: {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (data.length < 2) {
    return (
      <div
        className="flex items-center justify-center text-[10px] text-forex-text-muted"
        style={{ width, height }}
      >
        Not enough data
      </div>
    );
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = width / (data.length - 1);
  const points = data
    .map((v, i) => `${(i * stepX).toFixed(2)},${(height - 4 - ((v - min) / range) * (height - 8)).toFixed(2)}`)
    .join(' ');

  const areaPoints = `0,${height} ${points} ${width},${height}`;

  const gradientId = `spark-${color.replace('#', '')}`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#${gradientId})`} />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Progress bar with a color determined by value vs midpoint. */
export function MiniBar({
  value,
  max,
  min = 0,
  reverse = false,
  height = 4,
}: {
  value: number;
  max: number;
  min?: number;
  reverse?: boolean;
  height?: number;
}) {
  const clamped = Math.max(min, Math.min(max, value));
  const pct = max === min ? 0 : ((clamped - min) / (max - min)) * 100;
  const isPositive = reverse ? value < (min + max) / 2 : value >= (min + max) / 2;
  return (
    <div
      className="w-full rounded-full bg-white/5 overflow-hidden"
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={min}
      aria-valuemax={max}
    >
      <div
        className={cn(
          'h-full rounded-full transition-all duration-500',
          isPositive ? 'bg-forex-bullish/70' : 'bg-forex-bearish/70',
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/** Common inline label/value row used across stat widgets. */
export function StatRow({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-white/[0.04] last:border-0">
      <span className="text-[11px] text-forex-text-muted">{label}</span>
      <span className={cn('text-xs font-mono font-medium text-forex-text', valueClass)}>{value}</span>
    </div>
  );
}

/** Style object helper for CSS custom properties (used by strength meter). */
export function cssVars(vars: Record<string, string>): CSSProperties {
  return vars as CSSProperties;
}
