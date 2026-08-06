import Sidebar from '@/components/Sidebar';
import TopBar from '@/components/TopBar';
import LivePricesWidget from '@/components/widgets/LivePricesWidget';
import ChartWidget from '@/components/widgets/ChartWidget';
import AIRecommendationWidget from '@/components/widgets/AIRecommendationWidget';
import TrendWidget from '@/components/widgets/TrendWidget';
import EconomicCalendarWidget from '@/components/widgets/EconomicCalendarWidget';
import RiskCalculatorWidget from '@/components/widgets/RiskCalculatorWidget';
import CurrencyStrengthWidget from '@/components/widgets/CurrencyStrengthWidget';
import OpenOpportunitiesWidget from '@/components/widgets/OpenOpportunitiesWidget';
import TradeJournalWidget from '@/components/widgets/TradeJournalWidget';
import PerformanceWidget from '@/components/widgets/PerformanceWidget';
import { useDashboard } from '@/contexts/DashboardContext';
import { formatSymbolLabel } from '@/components/widgets/LivePricesWidget';

export default function DashboardPage() {
  const { activeSymbol, activeTimeframe } = useDashboard();

  return (
    <div className="min-h-screen bg-forex-bg flex">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 p-4 md:p-6 overflow-auto">
          {/* Active symbol strip */}
          <div className="flex flex-wrap items-center gap-2 mb-4 fade-in">
            <span className="glass-panel px-3 py-1.5 rounded-lg text-xs font-mono font-semibold text-forex-bullish border-forex-bullish/30">
              {formatSymbolLabel(activeSymbol)}
            </span>
            <span className="glass-panel px-3 py-1.5 rounded-lg text-xs font-mono text-forex-cyan">
              {activeTimeframe}
            </span>
            <span className="glass-panel px-3 py-1.5 rounded-lg text-[11px] text-forex-text-muted">
              Market Data · AI Advisory — no automated trading
            </span>
          </div>

          {/* Row 1 — Chart (wide) + Live Prices (sidebar) */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-4">
            <div className="md:col-span-2 xl:col-span-3 min-h-[460px]">
              <ChartWidget />
            </div>
            <div className="md:col-span-2 xl:col-span-1 min-h-[460px]">
              <LivePricesWidget />
            </div>
          </div>

          {/* Rows 2–3 — AI, Trend, Strength, Risk, Opportunities, Calendar */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-4">
            <div className="min-h-[400px]">
              <AIRecommendationWidget />
            </div>
            <div className="min-h-[400px]">
              <TrendWidget />
            </div>
            <div className="min-h-[400px]">
              <CurrencyStrengthWidget />
            </div>
            <div className="min-h-[400px]">
              <RiskCalculatorWidget />
            </div>
            <div className="min-h-[400px]">
              <OpenOpportunitiesWidget />
            </div>
            <div className="min-h-[400px]">
              <EconomicCalendarWidget />
            </div>
          </div>

          {/* Row 4 — Trade Journal (full width) */}
          <div className="mb-4 min-h-[320px]">
            <TradeJournalWidget />
          </div>

          {/* Row 5 — Performance Dashboard (full width) */}
          <div className="mb-4 min-h-[280px]">
            <PerformanceWidget />
          </div>

          {/* Footer */}
          <div className="mt-6 pt-4 border-t border-forex-border flex items-center justify-between text-xs text-forex-text-muted">
            <span>ForexAI Terminal v0.1.0 — Advisory Only</span>
            <span className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-forex-bullish animate-pulse" />
              System Online
            </span>
          </div>
        </main>
      </div>
    </div>
  );
}
