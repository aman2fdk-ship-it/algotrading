# ForexAI Terminal

Institutional-grade forex analysis terminal — browser-based dashboard with AI-powered trade recommendations, risk management, and trade journal.

**⚠️ Advisory only — not financial advice. No automated trading.**

## Tech Stack

- **Frontend:** React 18 + TypeScript + Tailwind CSS (Vite)
- **Backend:** FastAPI (Python 3.12)
- **Database:** PostgreSQL 16
- **Cache:** Redis 7
- **Orchestration:** Docker Compose

## Quick Start

```bash
# Clone and start all services
docker compose up --build

# The app will be available at:
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### First Run

1. Visit http://localhost:3000
2. Click "Create account" to register
3. Fill in your name, email, and password (min 8 characters)
4. You'll be redirected to the dashboard automatically
5. Explore the dashboard — all 10 widgets are implemented and wired to the API:
   Live Prices, Chart (TradingView), AI Recommendation, Trend, Risk Calculator,
   Economic Calendar, Currency Strength, Open Opportunities, Trade Journal, Performance
   (see [Known limitations](#known-limitations) below)

## Architecture

```
forexai-terminal/
├── docker-compose.yml          # 4 services: frontend, backend, postgres, redis
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI app with CORS, lifespan, router registration
│       ├── config.py           # Pydantic settings
│       ├── database.py         # Async SQLAlchemy + session
│       ├── models/             # SQLAlchemy ORM models
│       │   ├── user.py                              # Auth
│       │   ├── symbol.py                            # Market Data
│       │   ├── candle.py                            # Market Data
│       │   ├── tick.py                              # Market Data
│       │   ├── account.py                           # Market Data
│       │   ├── broker.py                            # Market Data
│       │   ├── market_status.py                     # Market Data
│       │   ├── technical_indicator.py               # Technical Analysis
│       │   ├── smc_structure.py                     # SMC
│       │   ├── ai_recommendation.py                 # AI Decision Engine
│       │   ├── risk_settings.py                     # Risk Management
│       │   └── backtest.py                          # Backtesting
│       ├── repositories/       # Data access layer
│       │   ├── symbol_repository.py                 # Market Data
│       │   ├── candle_repository.py                 # Market Data
│       │   ├── tick_repository.py                   # Market Data
│       │   ├── account_repository.py                # Market Data
│       │   ├── broker_repository.py                 # Market Data
│       │   ├── market_status_repository.py          # Market Data
│       │   ├── indicator_repository.py              # Technical Analysis
│       │   ├── smc_repository.py                    # SMC
│       │   ├── ai_recommendation_repo.py            # AI Decision Engine
│       │   ├── risk_repository.py                   # Risk Management
│       │   └── backtest_repository.py               # Backtesting
│       ├── services/           # Business logic & background services
│       │   ├── mt5_client.py                        # Market Data
│       │   ├── tick_collector.py                    # Market Data
│       │   ├── candle_sync.py                       # Market Data
│       │   ├── session_detector.py                  # Market Data
│       │   ├── market_status.py                     # Market Data
│       │   ├── reconnection.py                      # Market Data
│       │   ├── technical_analysis.py                # Technical Analysis
│       │   ├── indicator_calculator.py              # Technical Analysis
│       │   ├── smc_calculator.py                    # SMC
│       │   ├── smc_detection.py                     # SMC
│       │   ├── ai_decision.py                       # AI Decision Engine
│       │   ├── risk_calculator.py                   # Risk Management
│       │   ├── risk_settings_service.py             # Risk Management
│       │   ├── backtest_engine.py                   # Backtesting
│       │   └── backtest_metrics.py                  # Backtesting
│       ├── routers/            # API route handlers
│       │   ├── auth.py                              # /auth
│       │   ├── market_data.py                       # /api/v1 (symbols, candles, ticks, …)
│       │   ├── indicators.py                        # /api/v1 (indicators, S/R, fib)
│       │   ├── smc.py                               # /api/v1/smc
│       │   ├── ai.py                                # /api/v1/ai
│       │   ├── risk.py                              # /api/v1/risk
│       │   └── backtest.py                          # /api/v1/backtest
│       ├── schemas/            # Pydantic request/response schemas
│       │   ├── auth.py
│       │   ├── market_data.py
│       │   ├── indicators.py
│       │   ├── smc.py
│       │   ├── ai.py
│       │   ├── risk.py
│       │   └── backtest.py
│       └── utils/
│           ├── security.py     # JWT + bcrypt helpers
│           └── dependencies.py # Auth middleware
├── frontend/                   # React + TypeScript + Tailwind (Vite)
└── README.md
```

## API Endpoints

Complete route map, grouped by router (mirrors `backend/app/routers/`). Interactive docs: http://localhost:8000/docs.

### Auth (`/auth`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create account — body `{name, email, password}` → user + tokens |
| POST | `/auth/login` | Authenticate — body `{email, password}` → access/refresh tokens |
| POST | `/auth/forgot-password` | Request password reset |
| POST | `/auth/refresh` | Refresh access token |
| GET | `/auth/me` | Get current user profile |
| PATCH | `/auth/settings` | Update user settings |
| POST | `/auth/logout` | Logout |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |

### Market Data (`/api/v1`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/symbols` | List supported symbols |
| GET | `/api/v1/account` | MT5 account info |
| GET | `/api/v1/broker` | Broker info |
| GET | `/api/v1/price/{symbol}` | Latest bid/ask/spread |
| GET | `/api/v1/candles/{symbol}` | OHLCV candles — query: `timeframe`, `limit` |
| GET | `/api/v1/ticks/{symbol}` | Tick data |
| GET | `/api/v1/market-status` | Market status for all symbols |
| GET | `/api/v1/market-status/{symbol}` | Market status for one symbol |

### Technical Analysis (`/api/v1`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/indicators/{symbol}` | Latest N indicator values — query: `timeframe`, `limit` |
| GET | `/api/v1/indicators/{symbol}/latest` | Single latest indicator snapshot |
| GET | `/api/v1/support-resistance/{symbol}` | Support & resistance levels |
| GET | `/api/v1/fibonacci/{symbol}` | Fibonacci retracement levels |

### Smart Money Concepts (`/api/v1/smc`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/smc/{symbol}` | SMC structures — query: `timeframe` (default H1), `limit` |
| GET | `/api/v1/smc/{symbol}/fvg` | Fair value gaps |
| GET | `/api/v1/smc/{symbol}/liquidity` | Liquidity zones |
| GET | `/api/v1/smc/{symbol}/order-blocks` | Order blocks |
| GET | `/api/v1/smc/{symbol}/premium-discount` | Premium/discount zones |
| GET | `/api/v1/smc/{symbol}/type/{structure_type}` | Structures filtered by type (e.g. `bullish_order_block`) |

### AI Decision Engine (`/api/v1/ai`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ai/analyze` | Analyze one symbol — body `{symbol}` → decision (`BUY`/`SELL`/`WAIT`), confidence (0–100), entry/SL/TP, trend, market bias, risk level, reasoning |
| POST | `/api/v1/ai/analyze-batch` | Analyze up to 10 symbols — body `{symbols: [...]}` → list of decisions |
| GET | `/api/v1/ai/recommendation/{symbol}` | Latest stored recommendation for a symbol (404 if none — run `/ai/analyze` first) |
| GET | `/api/v1/ai/recommendations` | Recent recommendations — query: `limit`, optional `symbol` filter |

### Risk Management (`/api/v1/risk`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/risk/calculate` | Position sizing — body `{symbol, account_balance, risk_percentage, entry_price, stop_loss, leverage}` → position size, risk amount, lot sizes, required margin. Pure math, no DB writes |
| GET | `/api/v1/risk/pip-values` | Pip size and pip value per lot for all symbols |
| GET | `/api/v1/risk/limits` | Current risk limits |
| PUT | `/api/v1/risk/limits` | Update risk limits |
| GET | `/api/v1/risk/status` | Trading status vs. configured limits |
| POST | `/api/v1/risk/reset` | Reset risk limits to defaults |

### Backtesting (`/api/v1/backtest`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/backtest/run` | Run a backtest — body `{symbol, timeframe, start_date, end_date, initial_balance, risk_percentage}` → trades, equity curve, monthly performance, metrics |
| GET | `/api/v1/backtest/runs` | List past runs |
| GET | `/api/v1/backtest/runs/{run_id}` | Retrieve one run |
| DELETE | `/api/v1/backtest/runs/{run_id}` | Delete a run |

## Design

- **Theme:** Dark navy/charcoal (#0a0e17) base
- **Panels:** Glassmorphism with backdrop-blur, rgba(255,255,255,0.03) fill
- **Bullish:** Cyan/teal (#00d4aa)
- **Bearish:** Red/coral (#ff4d6a)
- **Font:** Inter (body), JetBrains Mono (data)
- **Responsive:** Fully responsive with CSS Grid layout

## Environment Variables

### Backend
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `JWT_SECRET` | `dev-secret-...` | JWT signing secret |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed origins |

### Frontend
| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8000` | Backend API URL |

## Development

```bash
# Backend only (with hot reload)
cd backend && uvicorn app.main:app --reload

# Frontend only (with hot reload)
cd frontend && npm run dev
```

## Migrations

Schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/) (versioned, auditable migrations with downgrades). Migration scripts live in `backend/alembic/versions/`; the database URL is read from the same `DATABASE_URL` environment variable the app uses (never hardcoded in `alembic.ini`).

```bash
# Apply all migrations (production / staging)
cd backend && alembic upgrade head

# Roll back the most recent migration
cd backend && alembic downgrade -1

# Autogenerate a new migration from ORM model changes
cd backend && alembic revision --autogenerate -m "describe change"
```

**Note:** the app still runs `Base.metadata.create_all` at startup — this is a development/test convenience so tests boot without running migrations. **Production should run `alembic upgrade head`** before starting the app; `create_all` will then be a no-op on an already-migrated database.

## Roadmap

All 8 modules are implemented and tested.

- [x] Auth & Dashboard Shell (MVP)
- [x] Market Data Engine (MT5 integration, candles, ticks)
- [x] Technical Analysis Engine (18+ indicators)
- [x] Smart Money Concepts (SMC)
- [x] AI Decision Engine
- [x] Backtesting module
- [x] Risk management tools
- [x] Trade journal with analytics
- [ ] Price alerts & notifications — **not yet built**

### Known limitations

- **Economic Calendar widget** renders static demo data (events generated relative to today); a live news feed is not wired up yet.
- **Trade Journal widget** persists entries in the browser's `localStorage` only — there is no backend sync, so entries do not follow the user across devices or browsers.

These are documented limitations, not regressions.

---

## Module 2: Market Data Engine

The Market Data Engine connects to MetaTrader 5 for live price feeds with auto-detection and reconnection. Background services handle live tick collection, candle synchronization, session detection, and market status monitoring.

### Database Models
- `Symbol` — 10 forex/crypto/commodity symbols with metadata
- `Candle` — OHLCV data per symbol × timeframe (M1,M5,M15,M30,H1,H4,D1)
- `Tick` — Bid/ask tick data with spread and volume
- `AccountInfo` — MT5 account balance, equity, margin, leverage
- `BrokerInfo` — Broker name, server, timezone, regulation
- `MarketStatus` — Per-symbol market open/close status and session

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/symbols` | List all supported symbols |
| GET | `/api/v1/account` | Get MT5 account information |
| GET | `/api/v1/broker` | Get broker information |
| GET | `/api/v1/price/{symbol}` | Get latest bid/ask/spread |
| GET | `/api/v1/candles/{symbol}` | Get OHLCV candles |
| GET | `/api/v1/ticks/{symbol}` | Get recent tick data |
| GET | `/api/v1/market-status` | Get market status for all symbols |
| GET | `/api/v1/market-status/{symbol}` | Get market status for one symbol |

---

## Module 3: Technical Analysis Engine

Calculates institutional-grade technical indicators from OHLCV candle data. All values are stored in PostgreSQL for fast retrieval — never recalculated redundantly. An event-driven background service auto-calculates indicators when new candles arrive.

### Indicators
**Trend:** EMA 20/50/200, SuperTrend, ADX
**Momentum:** RSI (14), MACD (12/26/9), Stochastic Oscillator (%K/%D)
**Volatility:** ATR (14), Bollinger Bands (20, 2σ)
**Volume:** VWAP
**Price Action:** Support & Resistance, Swing Highs/Lows, Fibonacci Retracement

### Database Model
`technical_indicators` — single denormalized table with all indicator values per symbol+timeframe+timestamp.

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/indicators/{symbol}` | Latest N indicator values |
| GET | `/api/v1/indicators/{symbol}/latest` | Single latest indicator snapshot |
| GET | `/api/v1/support-resistance/{symbol}` | Support & resistance levels |
| GET | `/api/v1/fibonacci/{symbol}` | Fibonacci retracement levels |

### Architecture
- `TechnicalAnalysisService` — pure Python indicator calculations (no pandas)
- `IndicatorCalculatorService` — asyncio background service with startup backfill + event-driven updates
- `IndicatorRepository` — upsert/query with deduplication
- Event hub pattern: CandleSynchronizer emits `candle_upserted` → IndicatorCalculatorService listens and calculates
