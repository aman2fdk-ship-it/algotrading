import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api, ApiError, type SMCStructureResponse } from '@/lib/api';
import { useDashboard } from '@/contexts/DashboardContext';
import { WidgetCard, WidgetSkeleton, ErrorState, EmptyState, MiniBar, cn } from './shared';
import { formatSymbolLabel } from './LivePricesWidget';
import { formatDateTime, formatPrice, formatPercent } from '@/lib/format';

/**
 * SMC Structures — renders Smart Money Concepts detected by the backend for the
 * active symbol/timeframe: order blocks, liquidity sweeps and fair value gaps
 * (GET /api/v1/smc/{symbol}/{order-blocks|liquidity|fvg}). A valid
 * symbol/timeframe with no detections returns 200 + empty arrays, which renders
 * a graceful empty state — never placeholder data.
 */
const SMC_LIMIT = 20;

interface SmcSections {
  orderBlocks: SMCStructureResponse[] | null;
  liquidity: SMCStructureResponse[] | null;
  fvg: SMCStructureResponse[] | null;
}

const STRUCTURE_LABELS: Record<string, string> = {
  order_block: 'Order block',
  liquidity_sweep: 'Liquidity sweep',
  fvg: 'Fair value gap',
};

function structureLabel(structureType: string): string {
  return STRUCTURE_LABELS[structureType] ?? structureType.replace(/_/g, ' ');
}

export default function SMCWidget() {
  const { activeSymbol, activeTimeframe } = useDashboard();
  const [sections, setSections] = useState<SmcSections>({ orderBlocks: null, liquidity: null, fvg: null });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);
    const [ob, liq, fvg] = await Promise.allSettled([
      api.getSmcOrderBlocks(activeSymbol, activeTimeframe, SMC_LIMIT),
      api.getSmcLiquidity(activeSymbol, activeTimeframe, SMC_LIMIT),
      api.getSmcFvg(activeSymbol, activeTimeframe, SMC_LIMIT),
    ]);
    if (requestIdRef.current !== requestId) return;
    setSections({
      orderBlocks: ob.status === 'fulfilled' ? ob.value.order_blocks : null,
      liquidity: liq.status === 'fulfilled' ? liq.value.liquidity_sweeps : null,
      fvg: fvg.status === 'fulfilled' ? fvg.value.fair_value_gaps : null,
    });
    if (ob.status === 'rejected' && liq.status === 'rejected' && fvg.status === 'rejected') {
      const first = (ob.reason ?? liq.reason ?? fvg.reason) as unknown;
      const message =
        first instanceof ApiError
          ? first.detail
          : first instanceof Error
            ? first.message
            : 'Failed to load SMC structures';
      setError(message);
      if (!(first instanceof ApiError && first.status === 401)) toast.error(message);
    }
    setIsLoading(false);
  }, [activeSymbol, activeTimeframe]);

  useEffect(() => {
    load();
    return () => {
      requestIdRef.current += 1;
    };
  }, [load]);

  const total = (sections.orderBlocks?.length ?? 0) + (sections.liquidity?.length ?? 0) + (sections.fvg?.length ?? 0);
  const hasAnyData = total > 0;

  const renderSection = (
    title: string,
    structures: SMCStructureResponse[] | null,
  ) => {
    const count = structures?.length ?? 0;
    const failed = structures === null;
    return (
      <div className="shrink-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] text-forex-text-muted uppercase tracking-wider">{title}</span>
          <span className={cn('text-[10px] font-mono px-1.5 py-0.5 rounded', count > 0 ? 'bg-forex-bullish/10 text-forex-bullish' : 'bg-white/5 text-forex-text-muted')}>
            {failed ? 'n/a' : count}
          </span>
        </div>
        {failed ? (
          <p className="text-[11px] text-forex-text-muted/70 mb-2">Unavailable — request failed.</p>
        ) : count === 0 ? (
          <p className="text-[11px] text-forex-text-muted mb-2">None detected on {activeTimeframe} yet.</p>
        ) : (
          <div className="space-y-1.5 mb-2">
            {structures?.map((s) => {
              const bullish = s.direction === 'bullish';
              const level =
                s.key_level !== null && s.key_level !== undefined
                  ? formatPrice(s.key_level)
                  : s.price_low !== null && s.price_high !== null
                    ? `${formatPrice(s.price_low)} – ${formatPrice(s.price_high)}`
                    : '—';
              return (
                <div key={s.id} className="rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={cn(
                        'text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide',
                        bullish ? 'bg-forex-bullish/10 text-forex-bullish' : 'bg-forex-bearish/10 text-forex-bearish',
                      )}
                    >
                      {s.direction}
                    </span>
                    <span className="text-[10px] font-mono text-forex-text-dim">{formatDateTime(s.timestamp)}</span>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[10px] text-forex-text-muted">{structureLabel(s.structure_type)}</span>
                    <span className="text-[11px] font-mono font-medium text-forex-text">{level}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <div className="flex-1">
                      <MiniBar value={s.confidence * 100} max={100} min={0} height={3} />
                    </div>
                    <span className="text-[10px] font-mono text-forex-text-muted w-11 text-right">
                      {formatPercent(s.confidence * 100, 0)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <WidgetCard
      title="SMC Structures"
      subtitle={`${formatSymbolLabel(activeSymbol)} · ${activeTimeframe} — Smart Money Concepts`}
      testId="smc-structures"
    >
      {isLoading && !hasAnyData && sections.orderBlocks === null ? (
        <WidgetSkeleton rows={8} />
      ) : error && !hasAnyData ? (
        <ErrorState message={error} onRetry={load} />
      ) : !hasAnyData ? (
        <EmptyState
          message={`No SMC structures detected for ${formatSymbolLabel(activeSymbol)} ${activeTimeframe} yet — the SMC calculator is still warming up.`}
        />
      ) : (
        <div className="h-full overflow-auto">
          {renderSection('Order Blocks', sections.orderBlocks)}
          {renderSection('Liquidity Sweeps', sections.liquidity)}
          {renderSection('Fair Value Gaps', sections.fvg)}
        </div>
      )}
    </WidgetCard>
  );
}
