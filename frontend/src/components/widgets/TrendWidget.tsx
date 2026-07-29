const trends = [
  { symbol: 'EUR/USD', trend: 'Bullish', strength: 72, bias: 'up' as const },
  { symbol: 'GBP/USD', trend: 'Bearish', strength: 58, bias: 'down' as const },
  { symbol: 'USD/JPY', trend: 'Bullish', strength: 65, bias: 'up' as const },
  { symbol: 'XAU/USD', trend: 'Strong Bullish', strength: 88, bias: 'up' as const },
];

export default function TrendWidget() {
  return (
    <div className="glass-panel p-5 h-full flex flex-col">
      <h3 className="text-sm font-semibold text-forex-text mb-4">Current Trends</h3>
      <div className="flex-1 space-y-3">
        {trends.map((t) => (
          <div key={t.symbol} className="flex items-center justify-between">
            <span className="font-mono text-xs font-medium w-20">{t.symbol}</span>
            <div className="flex-1 mx-3">
              <div className="h-1.5 rounded-full bg-forex-border overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    t.bias === 'up' ? 'bg-forex-bullish' : 'bg-forex-bearish'
                  }`}
                  style={{ width: `${t.strength}%` }}
                />
              </div>
            </div>
            <span
              className={`text-xs font-medium w-28 text-right ${
                t.bias === 'up' ? 'text-forex-bullish' : 'text-forex-bearish'
              }`}
            >
              {t.trend} ({t.strength}%)
            </span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-forex-text-muted mt-3 text-center">
        * Dummy trend data
      </p>
    </div>
  );
}
