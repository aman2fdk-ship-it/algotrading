const recommendations = [
  {
    symbol: 'EUR/USD',
    signal: 'BUY' as const,
    confidence: 78,
    entry: '1.0870',
    target: '1.0950',
    stop: '1.0820',
  },
  {
    symbol: 'GBP/USD',
    signal: 'SELL' as const,
    confidence: 64,
    entry: '1.2650',
    target: '1.2550',
    stop: '1.2710',
  },
  {
    symbol: 'XAU/USD',
    signal: 'BUY' as const,
    confidence: 85,
    entry: '2030',
    target: '2070',
    stop: '2010',
  },
];

const signalColors = {
  BUY: 'text-forex-bullish bg-forex-bullish-dim border-forex-bullish/30',
  SELL: 'text-forex-bearish bg-forex-bearish-dim border-forex-bearish/30',
  WAIT: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
};

export default function AIRecommendationWidget() {
  return (
    <div className="glass-panel p-5 h-full flex flex-col">
      <h3 className="text-sm font-semibold text-forex-text mb-4 flex items-center gap-2">
        <span>🤖</span> AI Recommendation
      </h3>
      <div className="flex-1 space-y-3 overflow-auto">
        {recommendations.map((rec) => (
          <div
            key={rec.symbol}
            className="p-3 rounded-lg bg-forex-surface/50 border border-forex-border hover:bg-forex-surface transition-all"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono font-semibold text-sm">{rec.symbol}</span>
              <span
                className={`inline-flex px-2.5 py-0.5 rounded text-xs font-bold border ${signalColors[rec.signal]}`}
              >
                {rec.signal}
              </span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <div className="flex-1 h-1.5 rounded-full bg-forex-border overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    rec.signal === 'BUY' ? 'bg-forex-bullish' : 'bg-forex-bearish'
                  }`}
                  style={{ width: `${rec.confidence}%` }}
                />
              </div>
              <span className="text-[10px] text-forex-text-muted font-mono w-8 text-right">
                {rec.confidence}%
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-[10px]">
              <div>
                <span className="text-forex-text-muted">Entry</span>
                <p className="font-mono text-forex-text">{rec.entry}</p>
              </div>
              <div>
                <span className="text-forex-text-muted">Target</span>
                <p className="font-mono text-forex-bullish">{rec.target}</p>
              </div>
              <div>
                <span className="text-forex-text-muted">Stop</span>
                <p className="font-mono text-forex-bearish">{rec.stop}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-forex-text-muted mt-3 text-center">
        * Advisory only — not financial advice
      </p>
    </div>
  );
}
