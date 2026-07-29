const dummyPrices = [
  { symbol: 'EUR/USD', bid: '1.0876', ask: '1.0878', change: '+0.12%', bullish: true },
  { symbol: 'GBP/USD', bid: '1.2645', ask: '1.2648', change: '-0.08%', bullish: false },
  { symbol: 'USD/JPY', bid: '152.34', ask: '152.37', change: '+0.34%', bullish: true },
  { symbol: 'AUD/USD', bid: '0.6521', ask: '0.6524', change: '-0.22%', bullish: false },
  { symbol: 'XAU/USD', bid: '2034.56', ask: '2035.10', change: '+1.24%', bullish: true },
  { symbol: 'BTC/USD', bid: '67890', ask: '67950', change: '+3.45%', bullish: true },
  { symbol: 'USD/CAD', bid: '1.3520', ask: '1.3523', change: '-0.05%', bullish: false },
  { symbol: 'USD/CHF', bid: '0.8845', ask: '0.8848', change: '+0.18%', bullish: true },
];

export default function LivePricesWidget() {
  return (
    <div className="glass-panel p-5 h-full flex flex-col">
      <h3 className="text-sm font-semibold text-forex-text mb-4 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-forex-bullish animate-pulse" />
        Live Forex Prices
      </h3>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-forex-text-muted border-b border-forex-border">
              <th className="text-left py-2 font-medium">Symbol</th>
              <th className="text-right py-2 font-medium">Bid</th>
              <th className="text-right py-2 font-medium">Ask</th>
              <th className="text-right py-2 font-medium">Change</th>
            </tr>
          </thead>
          <tbody>
            {dummyPrices.map((row) => (
              <tr key={row.symbol} className="border-b border-forex-border/50 hover:bg-white/[0.02]">
                <td className="py-2.5 font-mono font-medium text-forex-text">{row.symbol}</td>
                <td className="py-2.5 text-right font-mono">{row.bid}</td>
                <td className="py-2.5 text-right font-mono text-forex-text-dim">{row.ask}</td>
                <td
                  className={`py-2.5 text-right font-mono font-medium ${
                    row.bullish ? 'text-forex-bullish' : 'text-forex-bearish'
                  }`}
                >
                  {row.change}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-forex-text-muted mt-3 text-center">
        * Dummy data — real prices coming soon
      </p>
    </div>
  );
}
