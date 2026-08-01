# Windows Phase 4 — Runtime Manager and Paper Trading

## Architecture

The Windows Phase 4 runtime is a system-owned simulation boundary:

```text
Persisted Market Bars
  -> persisted Candidate Signal
  -> Trade Plan
  -> System Paper Order
  -> System Paper Fill
  -> System Paper Position
  -> valuation and deterministic exit
  -> immutable System Paper Review
  -> Strategy Scoreboard
```

`RuntimeManager` owns lifecycle only. `PaperScheduler` coordinates jobs, while
`PaperTradingService`, `SystemPaperReviewService`, and
`PaperPerformanceService` own business rules. Dashboard routes do not calculate
trading results.

The `system_paper_*` tables are not user holdings, broker positions, or the
legacy paper models. No broker account ID is stored or read.

## Runtime Manager

States are `STOPPED`, `STARTING`, `RUNNING`, `DEGRADED`, `STOPPING`, and
`FAILED`. Status includes process ID, database-lock ownership, current task,
last success, last failure, and the last sanitized result.

A persistent single-owner lock plus an in-process non-overlap lock prevents
concurrent runs and duplicate orders. Lock records expire and can be recovered
after an abnormal process exit. Windows shutdown and Ctrl+C flow through the
FastAPI lifespan and call `stop()`.

Autostart is disabled unless both `RUNTIME_MANAGER_ENABLED` and
`PAPER_TRADING_AUTOSTART` are explicitly enabled. Windows Phase 4 does not set
an operating-system startup task.

## Paper Account

The internal account has configurable USD initial cash. It records available
cash, reserved cash, signed position value, equity, realized and unrealized
P/L, daily P/L, cumulative return, peak equity, and maximum drawdown.

```text
Total Equity = Available Cash + Reserved Cash + signed Position Market Value
```

LONG positions use positive signed market value. SHORT positions use negative
signed market value while short-sale proceeds remain in cash. Gross-exposure
limits prevent the proceeds from creating unintended leverage.

## Paper Order, Fill, and Position

Trade Plan is the only entry source. A Plan must reference a persisted
`CANDIDATE_BUY` with `VALID` status and the same symbol, timeframe, strategy,
and strategy version. A stable key prevents a Plan from opening twice:

```text
paper-entry:{paper_account_id}:{trade_plan_id}:{direction}
```

Orders retain rejection codes, trigger price, trigger Bar, fill model, rule
version, and sanitized metadata. Every Fill records price, quantity, Bar time,
slippage, fee, and source. Positions retain original and remaining quantity,
entry and exit facts, MFE, MAE, target progress, data quality, and market-data
freshness.

## Fill Model: paper-fill-v1

- Only persisted Bars are used.
- Entry evaluates the first unprocessed Bar after the Trade Plan. It never
  scans a future Bar to decide an earlier fill.
- A LONG buy zone fills at its upper boundary; a SHORT zone fills at its lower
  boundary. These are deliberately no better than the plan.
- Breakout entries require the persisted breakout boundary to be crossed.
- LONG entry slippage increases price; SHORT entry slippage decreases price.
- LONG stop gaps fill at no better than `min(stop, bar open)` minus slippage.
- SHORT stop gaps mirror the LONG rule.
- Targets receive adverse slippage and never improve the planned target.
- If Stop and Target occur in one Bar, Stop wins and the reason is
  `AMBIGUOUS_STOP_PRIORITY`.
- Fractional shares are disabled unless explicitly configured.
- No future data, AI output, broker state, or live-order adapter participates.

## Position Sizing

Supported modes are `PERCENT_EQUITY` and `FIXED_CASH`. Configurable limits:

- fixed cash per trade;
- percentage of equity per trade;
- maximum open position count;
- maximum entries per Run Once;
- maximum symbol, strategy, and gross exposure;
- minimum cash reserve;
- same-symbol aggregation and strategy-coexistence policy;
- leverage and fractional-share switches.

The default permits one open position per symbol, prevents unintended scale-in,
keeps a cash reserve, and rejects rather than creating negative cash.

## Exit Rules: paper-exit-v1

The deterministic order is Safety/Data validation, Stop, Target, Plan
Cancellation/Expiry, and configured maximum holding period. AI never decides
an exit.

- Stop is a full exit.
- With multiple targets, Target 1 reduces the configured percentage and the
  final target closes the remainder.
- `MANUAL_CLOSE` and `SAFETY_CLOSE` require administrator authentication and a
  valid persisted Bar.
- Cancellation and expiry close at an adverse-slippage Bar close.
- Every exit records reason, trigger and fill price, trigger Bar, timestamp,
  and rule version.

## Valuation and Equity Curve

Open positions are valued from the latest valid persisted Bar. Data older than
the timeframe-specific threshold is marked `STALE`; missing or invalid data is
not presented as realtime. Decimal arithmetic is used for cash and P/L.

Snapshots can be written after entry, exit, manual revaluation, or scheduled
valuation. They store daily return, cumulative return, peak equity, current
drawdown, maximum drawdown, and source. Identical snapshots from the same source
are deduplicated.

## Review Flow

Only a completely closed `SystemPaperPosition` can create a final Review. The
review key is stable and repeated runs are idempotent:

```text
SYSTEM_PAPER:{position_id}:{fill_model_version}
```

The Review stores the exact entry, exit, holding time, realized return, MFE,
MAE, exit reason, target/stop flags, strategy and fill versions, data quality,
and a source snapshot. It does not recompute historical features or overwrite a
User Review. A Review failure occurs after the close commit and cannot roll the
position back.

## Strategy Scoreboard

The scoreboard reads only system Paper Trading positions. It provides total,
closed, and open trades; wins, losses, breakeven; win rate; average return,
win, and loss; profit factor; expectancy; MFE; MAE; holding time; total return;
maximum drawdown; current exposure; and the latest 30 closed trades.

Filters include strategy, version, symbol, market, timeframe, date range, and
direction. The sample size is displayed. Sharpe remains `—` because the current
data granularity is insufficient.

## Scheduler

The Scheduler contains job slots for Market Data Refresh, Feature Incremental,
Candidate Scan, Trade Plan Generation, Paper Entry, Exit Evaluation, Position
Valuation, Review, Scoreboard, and Equity Snapshot. It contains no business
rules.

Market, Feature, Candidate, and Plan background jobs remain `SAFE_DISABLED` in
Phase 4 so the Scheduler cannot start OpenD realtime. Each job records enabled
state, last and next run, duration, result, and sanitized error. SQLite lock
errors receive bounded exponential retry.

## API

Public read-only API:

- `GET /api/system-paper/account`
- `GET /api/system-paper/positions`
- `GET /api/system-paper/positions/{id}`
- `GET /api/system-paper/orders`
- `GET /api/system-paper/fills`
- `GET /api/system-paper/equity`
- `GET /api/system-paper/performance`
- `GET /api/system-paper/scoreboard`
- `GET /api/system-paper/runtime`
- `GET /api/system-paper/scheduler`
- `GET /api/system-paper/audit`

Administrator mutation endpoints are under `/internal/system-paper` and are
excluded from public OpenAPI. Legacy `/api/system-paper/runtime/*` aliases are
retained for compatibility but also hidden from public OpenAPI.

## Logging and Audit

Append-only audit events cover Candidate and Plan evaluation, order creation or
rejection, fills, position open/update/close, equity, Review, Scoreboard,
Runtime start/stop, and sanitized Runtime errors. The trace is:

```text
Candidate -> Trade Plan -> Paper Order -> Fill -> Position -> Review
```

Tokens, API keys, passwords, cookies, `.env`, broker account identifiers, and
complete user-private data are filtered from audit details.

## Safety Boundaries

- real order adapters and `place_order` are absent;
- Moomoo live trading and order submission remain false;
- Telegram send, webhook, and polling remain off;
- Gemini and all external AI transport remain off;
- OpenD realtime callbacks remain off;
- all Phase 4 runtime switches default false;
- the formal database and `.env` are excluded from Git.

## Windows Operations

The formal database is `E:\QuantPilotData\quantpilot.db`. Dashboard, Runtime,
CLI, and controlled smoke commands must resolve the same `DATABASE_URL`.

Dry Run is read-only:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/internal/system-paper/dry-run `
  -Headers @{"X-Dashboard-Token"="<local-admin-token>"} `
  -ContentType application/json -Body '{"max_entries":3}'
```

Controlled Run Once is bounded to at most three entries and does not start the
long-running Scheduler:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/internal/system-paper/run-once `
  -Headers @{"X-Dashboard-Token"="<local-admin-token>"} `
  -ContentType application/json -Body '{"max_entries":3}'
```

## Known Limitations

- The Scheduler is a durable-status, in-process coordinator rather than a
  distributed queue.
- Strategy Exit/Reduce candidates are reserved; Phase 4 implements Stop,
  multi-target partial/full exit, Plan cancellation/expiry, maximum holding,
  manual close, and safety close.
- Account values are persisted-market-data valuations, not broker realtime
  assets.
- A formal database with no executable Trade Plan correctly produces zero
  orders and positions.

## Phase 5 Handoff

Phase 5 may start only after migration, full tests, formal Dry Run, controlled
Run Once, security scans, browser smoke, local Commit, and clean Working Tree
all pass. Telegram Runtime must remain off until that handoff begins.
