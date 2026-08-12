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
5. Explore the dashboard with placeholder widgets

## Architecture

```
forexai-terminal/
├── docker-compose.yml          # 4 services: frontend, backend, postgres, redis
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI app with CORS, lifespan
│       ├── config.py           # Pydantic settings
│       ├── database.py         # Async SQLAlchemy + session
│       ├── models/             # SQLAlchemy ORM models
│       │   ├── user.py
│       │   ├── symbol.py
│       │   ├── candle.py
│       │   ├── tick.py
│       │   ├── account.py
│       │   ├── broker.py
│       │   ├── market_status.py
│       │   └── technical_indicator.py
│       ├── repositories/       # Data access layer
│       │   ├── symbol_repository.py
│       │   ├── candle_repository.py
│       │   ├── tick_repository.py
│       │   ├── account_repository.py
│       │   ├── broker_repository.py
│       │   ├── market_status_repository.py
│       │   └── indicator_repository.py
│       ├── services/           # Business logic & background services
│       │   ├── mt5_client.py
│       │   ├── tick_collector.py
│       │   ├── candle_sync.py
│       │   ├── session_detector.py
│       │   ├── market_status.py
│       │   ├── reconnection.py
│       │   ├── technical_analysis.py
│       │   └── indicator_calculator.py
│       ├── routers/            # API route handlers
│       │   ├── auth.py
│       │   ├── market_data.py
│       │   └── indicators.py
│       ├── schemas/            # Pydantic request/response schemas
│       │   ├── auth.py
│       │   ├── market_data.py
│       │   └── indicators.py
│       └── utils/
│           ├── security.py     # JWT + bcrypt helpers
│           └── dependencies.py # Auth middleware
├── frontend/                   # React + TypeScript + Tailwind (Vite)
└── README.md
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create new account |
| POST | `/auth/login` | Authenticate and get tokens |
| POST | `/auth/forgot-password` | Request password reset |
| POST | `/auth/refresh` | Refresh access token |
| GET | `/auth/me` | Get current user profile |
| PATCH | `/auth/settings` | Update user settings |
| POST | `/auth/logout` | Logout |
| GET | `/health` | Health check |
| GET | `/api/v1/symbols` | List supported symbols |
| GET | `/api/v1/account` | MT5 account info |
| GET | `/api/v1/broker` | Broker info |
| GET | `/api/v1/price/{symbol}` | Latest bid/ask |
| GET | `/api/v1/candles/{symbol}` | OHLCV candles |
| GET | `/api/v1/ticks/{symbol}` | Tick data |
| GET | `/api/v1/market-status` | Market status all symbols |
| GET | `/api/v1/market-status/{symbol}` | Market status one symbol |
| GET | `/api/v1/indicators/{symbol}` | Technical indicators |
| GET | `/api/v1/indicators/{symbol}/latest` | Latest indicator snapshot |
| GET | `/api/v1/support-resistance/{symbol}` | S/R levels |
| GET | `/api/v1/fibonacci/{symbol}` | Fibonacci levels |

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

- [x] Auth & Dashboard Shell (MVP)
- [x] Market Data Engine (MT5 integration, candles, ticks)
- [x] Technical Analysis Engine (18+ indicators)
- [ ] Smart Money Concepts (SMC)
- [ ] AI Decision Engine
- [ ] Backtesting module
- [ ] Risk management tools
- [ ] Trade journal with analytics
- [ ] Price alerts & notifications

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
