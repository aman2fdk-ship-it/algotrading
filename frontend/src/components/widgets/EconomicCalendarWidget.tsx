import { WidgetCard, cn } from './shared';

interface CalendarEvent {
  date: Date;
  time: string;
  event: string;
  currency: string;
  impact: 'High' | 'Medium' | 'Low';
  forecast: string | null;
  previous: string | null;
}

/**
 * Static demo calendar — events are generated relative to today so the
 * dashboard always looks current. A live feed is a future enhancement.
 */
function buildDummyEvents(): CalendarEvent[] {
  const now = new Date();
  const day = (offset: number) => {
    const d = new Date(now);
    d.setDate(d.getDate() + offset);
    return d;
  };
  return [
    { date: day(0), time: '08:30', event: 'US GDP (QoQ)', currency: 'USD', impact: 'High', forecast: '2.5%', previous: '3.1%' },
    { date: day(0), time: '14:00', event: 'FOMC Interest Rate Decision', currency: 'USD', impact: 'High', forecast: '5.50%', previous: '5.50%' },
    { date: day(1), time: '07:00', event: 'Japan Tokyo CPI (YoY)', currency: 'JPY', impact: 'Medium', forecast: '2.8%', previous: '2.6%' },
    { date: day(1), time: '10:00', event: 'EU Consumer Confidence', currency: 'EUR', impact: 'Medium', forecast: '-14.0', previous: '-14.5' },
    { date: day(2), time: '09:30', event: 'UK CPI (YoY)', currency: 'GBP', impact: 'High', forecast: '3.4%', previous: '3.2%' },
    { date: day(3), time: '12:30', event: 'US Initial Jobless Claims', currency: 'USD', impact: 'Medium', forecast: '215K', previous: '212K' },
    { date: day(4), time: '07:00', event: 'Germany IFO Business Climate', currency: 'EUR', impact: 'Low', forecast: '87.5', previous: '87.8' },
    { date: day(5), time: '08:30', event: 'Canada Retail Sales (MoM)', currency: 'CAD', impact: 'Low', forecast: '0.3%', previous: '-0.1%' },
  ];
}

const impactStyles = {
  High: 'text-forex-bearish bg-forex-bearish-dim border-forex-bearish/30',
  Medium: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  Low: 'text-forex-text-dim bg-white/5 border-white/10',
};

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export default function EconomicCalendarWidget() {
  const events = buildDummyEvents();
  const todayLabel = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });

  return (
    <WidgetCard
      title="Economic Calendar"
      subtitle={`Week of ${todayLabel} — demo data, live feed coming later`}
      testId="economic-calendar"
    >
      <div className="h-full flex flex-col">
        <div className="flex-1 overflow-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-forex-bg/80 backdrop-blur-sm z-10">
              <tr className="text-forex-text-muted border-b border-forex-border">
                <th className="text-left py-2 font-medium">Date</th>
                <th className="text-left py-2 font-medium">Event</th>
                <th className="text-center py-2 font-medium">Currency</th>
                <th className="text-right py-2 font-medium">Forecast</th>
                <th className="text-right py-2 font-medium">Previous</th>
                <th className="text-right py-2 font-medium">Impact</th>
              </tr>
            </thead>
            <tbody>
              {events.map((evt, i) => {
                const isToday = evt.date.toDateString() === new Date().toDateString();
                return (
                  <tr key={i} className="border-b border-forex-border/50 hover:bg-white/[0.02] transition-colors">
                    <td className="py-2.5 pr-3 text-forex-text-dim whitespace-nowrap">
                      <div className={cn('font-medium', isToday && 'text-forex-bullish')}>
                        {isToday ? 'Today' : DAY_NAMES[evt.date.getDay()]}, {evt.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      </div>
                      <div className="text-forex-text-muted">{evt.time}</div>
                    </td>
                    <td className="py-2.5 pr-3 font-medium">{evt.event}</td>
                    <td className="py-2.5 text-center">
                      <span className="inline-flex px-2 py-0.5 rounded bg-forex-surface border border-forex-border font-mono text-[10px]">
                        {evt.currency}
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-mono text-forex-text-dim">{evt.forecast}</td>
                    <td className="py-2.5 text-right font-mono text-forex-text-muted">{evt.previous}</td>
                    <td className="py-2.5 text-right">
                      <span className={cn('inline-flex px-2 py-0.5 rounded text-[10px] font-semibold border', impactStyles[evt.impact])}>
                        {evt.impact}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] text-forex-text-muted mt-3 text-center shrink-0">
          * Demo events for illustration — connect a live economic feed in a future module
        </p>
      </div>
    </WidgetCard>
  );
}
