import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '@/lib/api';

/**
 * Tests for the API client (src/lib/api.ts).
 * Uses a stubbed global fetch — no backend required.
 */

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const symbolsResponse = {
  symbols: [
    { code: 'EURUSD', name: 'EUR/USD', asset_type: 'forex', pip_size: 0.0001, digits: 5, enabled: true },
  ],
  count: 1,
};

describe('api', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    localStorage.clear();
  });

  describe('auth endpoints', () => {
    it('login posts credentials to /auth/login without auth header', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' }));
      localStorage.setItem('access_token', 'stale-token');

      await api.login({ email: 'a@b.c', password: 'pw' });

      const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      expect(url).toBe('/auth/login');
      expect(init.method).toBe('POST');
      expect(init.headers).not.toHaveProperty('Authorization');
      expect(JSON.parse(String(init.body))).toEqual({ email: 'a@b.c', password: 'pw' });
    });

    it('register posts to /auth/register', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' }));
      await api.register({ name: 'N', email: 'a@b.c', password: 'pw', confirm_password: 'pw' });
      expect(mockFetch.mock.calls[0][0]).toBe('/auth/register');
    });

    it('refreshToken posts refresh_token to /auth/refresh', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' }));
      await api.refreshToken('rt-123');
      const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      expect(mockFetch.mock.calls[0][0]).toBe('/auth/refresh');
      expect(JSON.parse(String(init.body))).toEqual({ refresh_token: 'rt-123' });
    });

    it('getMe calls /auth/me with bearer token', async () => {
      localStorage.setItem('access_token', 'tok-1');
      mockFetch.mockResolvedValueOnce(jsonResponse({ id: '1', email: 'a@b.c', name: 'N', is_active: true, is_verified: true, avatar_url: null, default_symbols: null, timezone: null, created_at: 'x', last_login: null }));
      await api.getMe();
      const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      expect(url).toBe('/auth/me');
      expect(init.headers).toHaveProperty('Authorization', 'Bearer tok-1');
    });
  });

  describe('market data + indicators endpoints', () => {
    it('getSymbols fetches /api/v1/symbols and parses response', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse(symbolsResponse));
      const res = await api.getSymbols();
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/symbols');
      expect(res.count).toBe(1);
      expect(res.symbols[0]?.code).toBe('EURUSD');
    });

    it('getPrice fetches /api/v1/price/{symbol}', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ symbol: 'EURUSD', bid: 1.1, ask: 1.1001, spread: 1, timestamp: 't' }));
      const res = await api.getPrice('EURUSD');
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/price/EURUSD');
      expect(res.bid).toBe(1.1);
    });

    it('getCandles builds timeframe/limit query and encodes values', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ candles: [], symbol: 'EURUSD', timeframe: 'H1', count: 0 }));
      await api.getCandles('EURUSD', 'H1', 200);
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/candles/EURUSD?timeframe=H1&limit=200');
    });

    it('getIndicators fetches with limit', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ indicators: [], symbol: 'EURUSD', timeframe: 'H1', count: 0 }));
      await api.getIndicators('EURUSD', 'H1', 100);
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/indicators/EURUSD?timeframe=H1&limit=100');
    });

    it('getMarketStatus fetches /api/v1/market-status', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ statuses: [], count: 0 }));
      await api.getMarketStatus();
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/market-status');
    });
  });

  describe('AI + risk + backtest endpoints', () => {
    it('getAIRecommendation POSTs symbol to /api/v1/ai/analyze', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ symbol: 'EURUSD', decision: 'BUY', confidence: 80 }));
      const res = await api.getAIRecommendation('EURUSD');
      const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/ai/analyze');
      expect(init.method).toBe('POST');
      expect(JSON.parse(String(init.body))).toEqual({ symbol: 'EURUSD' });
      expect(res.decision).toBe('BUY');
    });

    it('getAIRecommendations uses limit query', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ recommendations: [], count: 0 }));
      await api.getAIRecommendations(5);
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/ai/recommendations?limit=5');
    });

    it('calculateRisk POSTs the full payload', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ symbol: 'EURUSD', position_size: 1000 }));
      const params = {
        account_balance: 10000,
        risk_percentage: 1,
        entry_price: 1.085,
        stop_loss: 1.08,
        symbol: 'EURUSD',
        leverage: 100,
      };
      await api.calculateRisk(params);
      const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/risk/calculate');
      expect(JSON.parse(String(init.body))).toEqual(params);
    });

    it('getBacktestRuns uses limit query', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ runs: [], count: 0 }));
      await api.getBacktestRuns(5);
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/backtest/runs?limit=5');
    });

    it('getBacktestRun fetches a single run by id', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ id: 'run-1' }));
      await api.getBacktestRun('run-1');
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/backtest/runs/run-1');
    });
  });

  describe('error handling', () => {
    it('throws ApiError with server detail on non-200 (with JSON body)', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Symbol not found' }, 404));
      await expect(api.getPrice('FOOBAR')).rejects.toMatchObject({
        name: 'ApiError',
        status: 404,
        detail: 'Symbol not found',
      });
    });

    it('throws ApiError with stringified body when detail is absent', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ oops: true }, 500));
      await expect(api.getSymbols()).rejects.toMatchObject({ status: 500, detail: '{"oops":true}' });
    });

    it('falls back to a default message when the body is not JSON', async () => {
      mockFetch.mockResolvedValueOnce(new Response('Internal Server Error', { status: 500 }));
      const err = await api.getSymbols().catch((e: unknown) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(500);
      expect((err as ApiError).detail).toBe('An error occurred');
    });

    it('propagates network failures', async () => {
      mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
      await expect(api.getSymbols()).rejects.toThrow('Failed to fetch');
    });

    it('does not redirect for 401 responses when skipAuth is set', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'bad' }, 401));
      // If the skipAuth path tried to redirect, jsdom would throw a
      // "navigation not implemented" error — so a clean rejection is the assertion.
      await expect(api.login({ email: 'a@b.c', password: 'pw' })).rejects.toMatchObject({ status: 401 });
      expect(window.location.href).not.toBe('/login');
    });

    it('clears tokens and attempts the /login redirect on 401', async () => {
      localStorage.setItem('access_token', 'tok');
      localStorage.setItem('refresh_token', 'ref');
      // jsdom cannot perform real navigation; when location.href is assigned it
      // logs "Not implemented: navigation" via the virtual console. Spy on it to
      // verify the redirect was attempted, and silence the expected noise.
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'expired' }, 401));
      await expect(api.getSymbols()).rejects.toMatchObject({
        name: 'ApiError',
        status: 401,
        detail: 'Session expired — please log in again',
      });

      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('refresh_token')).toBeNull();
      expect(String(consoleSpy.mock.calls[0]?.[0])).toContain('Not implemented: navigation');
      consoleSpy.mockRestore();
    });
  });

  describe('P1 widget endpoints (ticks / SMC / fibonacci)', () => {
    it('getTicks fetches /api/v1/ticks/{symbol} with limit', async () => {
      mockFetch.mockResolvedValueOnce(
        jsonResponse({ ticks: [{ symbol: 'EURUSD', timestamp: 't', bid: 1.1, ask: 1.1002, spread: 2, volume: 5 }], symbol: 'EURUSD', count: 1 }),
      );
      const res = await api.getTicks('EURUSD', 30);
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/ticks/EURUSD?limit=30');
      expect(res.count).toBe(1);
      expect(res.ticks[0]?.bid).toBe(1.1);
    });
    it('getSmcOrderBlocks builds the order-blocks URL with timeframe and limit', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ order_blocks: [], symbol: 'EURUSD', timeframe: 'H1', count: 0 }));
      const res = await api.getSmcOrderBlocks('EURUSD', 'H1', 20);
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/smc/EURUSD/order-blocks?timeframe=H1&limit=20');
      expect(res.count).toBe(0);
    });
    it('getSmcLiquidity builds the liquidity URL', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ liquidity_sweeps: [], symbol: 'EURUSD', timeframe: 'H1', count: 0 }));
      await api.getSmcLiquidity('EURUSD', 'H1');
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/smc/EURUSD/liquidity?timeframe=H1&limit=20');
    });
    it('getSmcFvg builds the fvg URL', async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse({ fair_value_gaps: [], symbol: 'EURUSD', timeframe: 'H1', count: 0 }));
      await api.getSmcFvg('EURUSD', 'H1', 10);
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/smc/EURUSD/fvg?timeframe=H1&limit=10');
    });
    it('getFibonacci fetches /api/v1/fibonacci/{symbol} with timeframe', async () => {
      mockFetch.mockResolvedValueOnce(
        jsonResponse({ symbol: 'EURUSD', timeframe: 'H1', timestamp: 't', fib_0: 0, fib_236: 1.09, fib_382: 1.092, fib_500: 1.094, fib_618: 1.096, fib_786: 1.098, fib_1: 0 }),
      );
      const res = await api.getFibonacci('EURUSD', 'H1');
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/fibonacci/EURUSD?timeframe=H1');
      expect(res.fib_618).toBe(1.096);
    });
    it('getSupportResistance fetches /api/v1/support-resistance/{symbol} with timeframe', async () => {
      mockFetch.mockResolvedValueOnce(
        jsonResponse({ symbol: 'EURUSD', timeframe: 'H1', timestamp: 't', support_levels: [1.08], resistance_levels: [1.11] }),
      );
      const res = await api.getSupportResistance('EURUSD', 'H1');
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/support-resistance/EURUSD?timeframe=H1');
      expect(res.support_levels).toEqual([1.08]);
    });
    it('encodes timeframe values in URLs', async () => {
      mockFetch.mockResolvedValue(jsonResponse({ symbol: 'EURUSD', timeframe: 'M5', timestamp: 't', support_levels: [], resistance_levels: [] }));
      await api.getSupportResistance('EURUSD', 'M5');
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/support-resistance/EURUSD?timeframe=M5');
    });
  });
});
