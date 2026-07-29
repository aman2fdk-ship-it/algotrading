const dummyEvents = [
  {
    date: 'Mon, Jul 22',
    time: '08:30',
    event: 'US GDP (QoQ)',
    currency: 'USD',
    impact: 'High' as const,
  },
  {
    date: 'Tue, Jul 23',
    time: '10:00',
    event: 'EU Consumer Confidence',
    currency: 'EUR',
    impact: 'Medium' as const,
  },
  {
    date: 'Wed, Jul 24',
    time: '09:30',
    event: 'UK CPI (YoY)',
    currency: 'GBP',
    impact: 'High' as const,
  },
  {
    date: 'Thu, Jul 25',
    time: '14:00',
    event: 'FOMC Interest Rate Decision',
    currency: 'USD',
    impact: 'High' as const,
  },
  {
    date: 'Fri, Jul 26',
    time: '07:00',
    event: 'Japan Tokyo CPI',
    currency: 'JPY',
    impact: 'Medium' as const,
  },
];

const impactColors = {
  High: 'text-forex-bearish bg-forex-bearish-dim',
  Medium: 'text-yellow-400 bg-yellow-400/10',
  Low: 'text-forex-text-dim bg-white/5',
};

export default function EconomicCalendarWidget() {
  return (
    <div className="glass-panel p-5 h-full flex flex-col">
      <h3 className="text-sm font-semibold text-forex-text mb-4">Economic Calendar</h3>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-forex-text-muted border-b border-forex-border">
              <th className="text-left py-2 font-medium">Date</th>
              <th className="text-left py-2 font-medium">Event</th>
              <th className="text-center py-2 font-medium">Currency</th>
              <th className="text-right py-2 font-medium">Impact</th>
            </tr>
          </thead>
          <tbody>
            {dummyEvents.map((evt, i) => (
              <tr key={i} className="border-b border-forex-border/50 hover:bg-white/[0.02]">
                <td className="py-2.5 text-forex-text-dim">
                  <div>{evt.date}</div>
                  <div className="text-forex-text-muted">{evt.time}</div>
                </td>
                <td className="py-2.5 font-medium">{evt.event}</td>
                <td className="py-2.5 text-center">
                  <span className="inline-flex px-2 py-0.5 rounded bg-forex-surface border border-forex-border font-mono text-[10px]">
                    {evt.currency}
                  </span>
                </td>
                <td className="py-2.5 text-right">
                  <span
                    className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold ${impactColors[evt.impact]}`}
                  >
                    {evt.impact}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-forex-text-muted mt-3 text-center">
        * Dummy calendar — real data coming soon
      </p>
    </div>
  );
}
