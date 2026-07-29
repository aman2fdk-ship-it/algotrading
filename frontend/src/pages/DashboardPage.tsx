import Sidebar from '@/components/Sidebar';
import TopBar from '@/components/TopBar';
import LivePricesWidget from '@/components/widgets/LivePricesWidget';
import ChartWidget from '@/components/widgets/ChartWidget';
import AIRecommendationWidget from '@/components/widgets/AIRecommendationWidget';
import TrendWidget from '@/components/widgets/TrendWidget';
import EconomicCalendarWidget from '@/components/widgets/EconomicCalendarWidget';

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-forex-bg flex">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 p-6 overflow-auto">
          {/* Widget grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 auto-rows-min">
            {/* Chart widget — spans 2 cols on xl */}
            <div className="md:col-span-2 xl:col-span-2 min-h-[380px]">
              <ChartWidget />
            </div>

            {/* Prices widget */}
            <div className="min-h-[380px]">
              <LivePricesWidget />
            </div>

            {/* AI Recommendation */}
            <div className="min-h-[340px]">
              <AIRecommendationWidget />
            </div>

            {/* Trend widget */}
            <div className="min-h-[340px]">
              <TrendWidget />
            </div>

            {/* Economic Calendar — spans full width */}
            <div className="md:col-span-2 xl:col-span-3 min-h-[320px]">
              <EconomicCalendarWidget />
            </div>
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
