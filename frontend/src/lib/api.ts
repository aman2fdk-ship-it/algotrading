const API_BASE = import.meta.env.VITE_API_URL || '';

interface ApiOptions extends RequestInit {
  skipAuth?: boolean;
}

class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.name = 'ApiError';
  }
}

/**
 * Redirect to the login page once per auth failure, clearing stale tokens.
 */
let redirectingToLogin = false;
function handleUnauthorized(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  if (!redirectingToLogin) {
    redirectingToLogin = true;
    window.location.href = '/login';
  }
}

async function request<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
  const { skipAuth, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((fetchOptions.headers as Record<string, string>) || {}),
  };

  if (!skipAuth) {
    const token = localStorage.getItem('access_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, { ...fetchOptions, headers });

  if (response.status === 401 && !skipAuth) {
    handleUnauthorized();
    throw new ApiError(401, 'Session expired — please log in again');
  }

  if (!response.ok) {
    let detail = 'An error occurred';
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // use default
    }
    throw new ApiError(response.status, detail);
  }

  return response.json();
}

/* ── Auth ─────────────────────────────────────────────────────────────────── */

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  is_verified: boolean;
  avatar_url: string | null;
  default_symbols: string | null;
  timezone: string | null;
  created_at: string;
  last_login: string | null;
}

export interface MessageResponse {
  message: string;
}

/* ── Market Data ──────────────────────────────────────────────────────────── */

export interface SymbolResponse {
  code: string;
  name: string;
  asset_type: string;
  pip_size: number;
  digits: number;
  enabled: boolean;
}

export interface SymbolListResponse {
  symbols: SymbolResponse[];
  count: number;
}

export interface PriceResponse {
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp: string;
}

export interface CandleResponse {
  symbol: string;
  timeframe: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  tick_volume: number;
  real_volume: number;
  spread: number;
}

export interface CandleListResponse {
  candles: CandleResponse[];
  symbol: string;
  timeframe: string;
  count: number;
}

export interface MarketStatusResponse {
  symbol: string;
  is_open: boolean;
  session: string;
  last_updated: string | null;
}

export interface TickResponse {
  symbol: string;
  timestamp: string;
  bid: number;
  ask: number;
  spread: number;
  volume: number;
}
export interface TickListResponse {
  ticks: TickResponse[];
  symbol: string;
  count: number;
}
/* SMC (Smart Money Concepts) */
export interface SMCStructureResponse {
  id: string;
  symbol: string;
  timeframe: string;
  timestamp: string;
  structure_type: string;
  direction: string;
  price_low: number | null;
  price_high: number | null;
  price_mid: number | null;
  key_level: number | null;
  confidence: number;
  details: string | null;
  created_at: string;
}
export interface SMCOrderBlockResponse {
  order_blocks: SMCStructureResponse[];
  symbol: string;
  timeframe: string;
  count: number;
}
export interface SMCLiquidityResponse {
  liquidity_sweeps: SMCStructureResponse[];
  symbol: string;
  timeframe: string;
  count: number;
}
export interface SMCFVGResponse {
  fair_value_gaps: SMCStructureResponse[];
  symbol: string;
  timeframe: string;
  count: number;
}
export interface SupportResistanceResponse {
  symbol: string;
  timeframe: string;
  timestamp: string;
  support_levels: number[];
  resistance_levels: number[];
}
export interface FibonacciResponse {
  symbol: string;
  timeframe: string;
  timestamp: string;
  fib_0: number;
  fib_236: number;
  fib_382: number;
  fib_500: number;
  fib_618: number;
  fib_786: number;
  fib_1: number;
}
/* ── Indicators ───────────────────────────────────────────────────────────── */

export interface IndicatorResponse {
  symbol: string;
  timeframe: string;
  timestamp: string;
  ema_20: number | null;
  ema_50: number | null;
  ema_200: number | null;
  supertrend_direction: number | null;
  supertrend_value: number | null;
  adx: number | null;
  rsi: number | null;
  macd_line: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  stoch_k: number | null;
  stoch_d: number | null;
  atr: number | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  vwap: number | null;
  support_levels: number[] | null;
  resistance_levels: number[] | null;
  swing_high: number | null;
  swing_low: number | null;
  fib_236: number | null;
  fib_382: number | null;
  fib_500: number | null;
  fib_618: number | null;
  fib_786: number | null;
}

export interface IndicatorLatestResponse {
  /** null when the symbol+timeframe is valid but no indicator rows exist yet. */
  indicator: IndicatorResponse | null;
}

/* ── AI Decision Engine ───────────────────────────────────────────────────── */

export interface TimeframeScoreDetail {
  timeframe: string;
  score: number;
  weight: number;
  category_scores: Record<string, number>;
}

export interface DecisionResult {
  symbol: string;
  decision: 'BUY' | 'SELL' | 'WAIT';
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit_1: number | null;
  take_profit_2: number | null;
  risk_reward_ratio: number | null;
  trend: string;
  market_bias: string;
  risk_level: string;
  reasoning: string;
  timeframe_scores: Record<string, number>;
  timeframe_details: TimeframeScoreDetail[];
  created_at: string | null;
}

export interface RecommendationResponse {
  id: string;
  symbol: string;
  decision: 'BUY' | 'SELL' | 'WAIT';
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit_1: number | null;
  take_profit_2: number | null;
  risk_reward_ratio: number | null;
  trend: string;
  market_bias: string;
  risk_level: string;
  reasoning: string;
  timeframe_scores: Record<string, number>;
  created_at: string;
}

export interface RecommendationListResponse {
  recommendations: RecommendationResponse[];
  count: number;
}

/* ── Risk Management ──────────────────────────────────────────────────────── */

export interface RiskCalculateRequest {
  account_balance: number;
  risk_percentage: number;
  entry_price: number;
  stop_loss: number;
  symbol: string;
  leverage: number;
}

export interface RiskCalculateResponse {
  symbol: string;
  account_balance: number;
  risk_percentage: number;
  entry_price: number;
  stop_loss: number;
  leverage: number;
  position_size: number;
  risk_amount: number;
  stop_loss_pips: number;
  lot_size: number;
  mini_lots: number;
  micro_lots: number;
  required_margin: number;
  take_profit_1: number | null;
  take_profit_2: number | null;
  potential_profit_tp1: number | null;
  potential_profit_tp2: number | null;
  risk_reward_ratio_tp1: number | null;
  risk_reward_ratio_tp2: number | null;
  pip_size: number;
  pip_value: number;
}

export interface PipValueItem {
  symbol: string;
  pip_size: number;
  pip_value_per_lot: number;
}

export interface PipValuesResponse {
  symbols: PipValueItem[];
  count: number;
}

/* ── Backtest ─────────────────────────────────────────────────────────────── */

export interface BacktestRunSummary {
  id: string;
  user_id: string;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_balance: number;
  risk_percentage: number;
  final_balance: number;
  total_trades: number;
  win_rate: number;
  profit_factor: number | null;
  max_drawdown: number;
  expectancy: number;
  sharpe_ratio: number | null;
  created_at: string;
}

export interface BacktestRunListResponse {
  runs: BacktestRunSummary[];
  count: number;
}

export interface EquityCurvePoint {
  timestamp: string;
  balance: number;
}

export interface BacktestTradeResponse {
  id: string;
  symbol: string;
  timeframe: string;
  direction: string;
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  position_size: number;
  pnl: number;
  pnl_pct: number;
  exit_reason: string;
  created_at: string;
}

export interface BacktestResultResponse extends BacktestRunSummary {
  avg_win: number | null;
  avg_loss: number | null;
  largest_win: number | null;
  largest_loss: number | null;
  avg_hold_time: number | null;
  equity_curve: EquityCurvePoint[];
  trades: BacktestTradeResponse[];
}

/* ── API surface ──────────────────────────────────────────────────────────── */

export const api = {
  /* Auth */
  register: (data: { name: string; email: string; password: string; confirm_password: string }) =>
    request<TokenResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    }),

  login: (data: { email: string; password: string }) =>
    request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    }),

  forgotPassword: (data: { email: string }) =>
    request<MessageResponse>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    }),

  refreshToken: (refreshToken: string) =>
    request<TokenResponse>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
      skipAuth: true,
    }),

  getMe: () => request<UserResponse>('/auth/me'),

  updateSettings: (data: { name?: string; default_symbols?: string; timezone?: string }) =>
    request<UserResponse>('/auth/settings', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  logout: () => request<MessageResponse>('/auth/logout', { method: 'POST' }),

  /* Market Data */
  getSymbols: () => request<SymbolListResponse>('/api/v1/symbols'),

  getPrice: (symbol: string) => request<PriceResponse>(`/api/v1/price/${symbol}`),

  getCandles: (symbol: string, timeframe: string, limit = 200) =>
    request<CandleListResponse>(
      `/api/v1/candles/${symbol}?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
    ),

  getMarketStatus: () => request<{ statuses: MarketStatusResponse[]; count: number }>('/api/v1/market-status'),
  getTicks: (symbol: string, limit = 50) =>
    request<TickListResponse>(`/api/v1/ticks/${symbol}?limit=${limit}`),
  /* SMC */
  getSmcOrderBlocks: (symbol: string, timeframe: string, limit = 20) =>
    request<SMCOrderBlockResponse>(
      `/api/v1/smc/${symbol}/order-blocks?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
    ),
  getSmcLiquidity: (symbol: string, timeframe: string, limit = 20) =>
    request<SMCLiquidityResponse>(
      `/api/v1/smc/${symbol}/liquidity?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
    ),
  getSmcFvg: (symbol: string, timeframe: string, limit = 20) =>
    request<SMCFVGResponse>(
      `/api/v1/smc/${symbol}/fvg?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
    ),
  getSupportResistance: (symbol: string, timeframe: string) =>
    request<SupportResistanceResponse>(
      `/api/v1/support-resistance/${symbol}?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  getFibonacci: (symbol: string, timeframe: string) =>
    request<FibonacciResponse>(
      `/api/v1/fibonacci/${symbol}?timeframe=${encodeURIComponent(timeframe)}`,
    ),

  /* Indicators */
  getIndicators: (symbol: string, timeframe: string, limit = 100) =>
    request<{ indicators: IndicatorResponse[]; symbol: string; timeframe: string; count: number }>(
      `/api/v1/indicators/${symbol}?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
    ),

  getLatestIndicator: (symbol: string, timeframe: string) =>
    request<IndicatorLatestResponse>(
      `/api/v1/indicators/${symbol}/latest?timeframe=${encodeURIComponent(timeframe)}`,
    ),

  /* AI Decision Engine */
  getAIRecommendation: (symbol: string) =>
    request<DecisionResult>('/api/v1/ai/analyze', {
      method: 'POST',
      body: JSON.stringify({ symbol }),
    }),

  getAIRecommendations: (limit = 5) =>
    request<RecommendationListResponse>(`/api/v1/ai/recommendations?limit=${limit}`),

  /* Risk Management */
  calculateRisk: (params: RiskCalculateRequest) =>
    request<RiskCalculateResponse>('/api/v1/risk/calculate', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  getPipValues: () => request<PipValuesResponse>('/api/v1/risk/pip-values'),

  /* Backtest */
  getBacktestRuns: (limit = 5) =>
    request<BacktestRunListResponse>(`/api/v1/backtest/runs?limit=${limit}`),

  getBacktestRun: (runId: string) =>
    request<BacktestResultResponse>(`/api/v1/backtest/runs/${runId}`),

  runBacktest: (params: {
    symbol: string;
    timeframe: string;
    start_date: string;
    end_date: string;
    initial_balance: number;
    risk_percentage: number;
  }) =>
    request<BacktestResultResponse>('/api/v1/backtest/run', {
      method: 'POST',
      body: JSON.stringify(params),
    }),
};

export { ApiError };
export type { ApiOptions };
