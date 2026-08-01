# Windows Phase 4 — System Paper Runtime

## Boundary

The Phase 4 ledger is isolated in `system_paper_*` tables. It is not a broker
account, a user portfolio, or the legacy `paper_positions` model. No Moomoo
trading API, live account, Telegram transport, Gemini transport, webhook, or
polling is called.

## Flow

`Trade Plan -> System Paper Order -> Paper Fill -> Paper Position -> Valuation
-> Exit -> Trade Review -> Strategy Scoreboard`

Trade Plan is the only entry source. The stable key
`paper-entry:{account_id}:{trade_plan_id}:{direction}` prevents duplicate entry
after retries or restart. Missing entry levels become `WAITING_ENTRY_DATA` and
never fall back to an arbitrary market price.

## paper-fill-v1

- persisted bar data only;
- midpoint of a persisted buy zone, otherwise persisted reference price;
- the bar must touch the level and must not predate the Trade Plan;
- configurable slippage, fixed fee, initial cash and position percentage;
- integer shares unless fractional trading is explicitly enabled;
- no leverage and no negative cash by default;
- when stop and target occur in the same bar, stop has conservative priority;
- LONG entry is implemented; SHORT entry remains `WAITING_UNSUPPORTED_DIRECTION`.

## Runtime

`RuntimeManager` coordinates `PaperTradingRuntime`, `ReviewRuntime` and
`StatisticsRuntime`. Business calculations remain in services. All lifecycle
switches are safe-off by default. The read-only API never starts the runtime.
Start, stop and process-once require administrator authentication.

## API and UI

- `GET /api/system-paper/account`
- `GET /api/system-paper/positions`
- `GET /api/system-paper/orders`
- `GET /api/system-paper/equity`
- `GET /api/system-paper/scoreboard`
- `GET /api/system-paper/runtime`
- `/dashboard/paper-positions`
- `/dashboard/strategy-scoreboard`
- `GET /api/telegram-preview/system-paper/account`

Telegram Preview is generated from the same persisted facts as the Dashboard.
It does not send a message or start Telegram Runtime.

## Accounting

`Total Equity = Available Cash + Reserved Cash + Position Market Value`.
Each valuation persists cash, position value, equity, total return and drawdown.
Closed positions retain entry, exit, MFE, MAE, realized P/L and exit reason.

## Known limits

- OpenD realtime remains disabled, so only newly persisted bars drive later cycles.
- No SHORT simulation in `paper-fill-v1`.
- The scheduler is in-process, not a durable distributed queue.
- Gemini and Telegram transport remain disabled in Phase 4.
