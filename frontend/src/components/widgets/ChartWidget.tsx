export default function ChartWidget() {
  return (
    <div className="glass-panel p-5 h-full flex flex-col">
      <h3 className="text-sm font-semibold text-forex-text mb-4">TradingView Chart</h3>
      <div className="flex-1 flex items-center justify-center rounded-lg bg-forex-surface/50 border border-forex-border min-h-[280px]">
        <div className="text-center">
          <svg
            className="w-12 h-12 mx-auto mb-3 text-forex-text-muted"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1}
              d="M3 17l6-6 4 4 8-8m0 0h-6m6 0v6"
            />
          </svg>
          <p className="text-sm text-forex-text-dim font-medium">EUR/USD • 1H</p>
          <p className="text-xs text-forex-text-muted mt-1">
            Chart widget — TradingView integration coming soon
          </p>
        </div>
      </div>
    </div>
  );
}
