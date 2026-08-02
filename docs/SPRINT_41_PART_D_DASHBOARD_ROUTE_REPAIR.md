# Sprint 41 Part D — Dashboard Route Repair and Mac Handoff

## Root cause

Part C added the final information architecture after the previously running FastAPI process had been started.
The browser therefore reached an old route table and returned JSON `404 Not Found` for the new pages. The latest
source already included the router, but had not yet completed route/process verification. Part D adds explicit route
coverage, validates every Sidebar link against the registered FastAPI routes, and requires a fresh process for UI QA.

## Route audit

All pages use the existing `app/dashboard/templates/dashboard.html` shell and the existing Dashboard login guard.
No second template framework or API endpoint was introduced.

| Group | Page | URL | Route name | Page id | Admin login | Test |
|---|---|---|---|---|---|---|
| Workspace | Dashboard | `/dashboard` | `home` | `home` | Yes | Yes |
| Market | Market Regime | `/dashboard/market-regime` | `market_regime` | `market-regime` | Yes | Yes |
| Market | Market Monitor | `/dashboard/market-monitor` | `market_monitor` | `market-monitor` | Yes | Yes |
| Market | Candidate Pool | `/dashboard/candidates` | `candidates` | `candidates` | Yes | Yes |
| Strategy | Trade Plans | `/dashboard/trade-plans` | `trade_plans` | `trade-plans` | Yes | Yes |
| Strategy | Paper Positions | `/dashboard/paper-positions` | `paper_positions` | `paper-positions` | Yes | Yes |
| Strategy | Trade Reviews | `/dashboard/trade-reviews` | `trade_reviews` | `trade-reviews` | Yes | Yes |
| Strategy | Strategy Scoreboard | `/dashboard/strategy-scoreboard` | `strategy_scoreboard` | `strategy-scoreboard` | Yes | Yes |
| AI | AI Trade Interpretation | `/dashboard/companion` | `companion` | `companion` | Yes | Yes |
| AI | AI Strategy Review | `/dashboard/ai-reviews` | `ai_reviews` | `ai-reviews` | Yes | Yes |
| AI | Telegram Preview | `/dashboard/telegram-preview` | `telegram_preview` | `telegram-preview` | Yes | Yes |
| Product | User Feedback | `/dashboard/product/feedback` | `product_feedback` | `product-feedback` | Yes | Yes |
| Product | User Behavior | `/dashboard/product/behavior` | `product_behavior` | `product-behavior` | Yes | Yes |
| Product | Bot Statistics | `/dashboard/product/bot-statistics` | `bot_statistics` | `bot-statistics` | Yes | Yes |
| Product | User Intelligence | `/dashboard/product/user-intelligence` | `user_intelligence` | `user-intelligence` | Yes | Yes |
| Lab | Strategy Experiments | `/dashboard/strategies` | `strategies` | `strategies` | Yes | Yes |
| Lab | Parameter Comparison | `/dashboard/strategy-lab/parameters` | `strategy_parameters` | `strategy-parameters` | Yes | Yes |
| Lab | Research Center | `/dashboard/research` | `research` | `research` | Yes | Yes |
| More | Version Center | `/dashboard/system` | `system` | `system` | Yes | Yes |
| More | System Monitor | `/dashboard/system-monitor` | `system_monitor` | `system-monitor` | Yes | Yes |
| More | Runtime Logs | `/dashboard/runtime-logs` | `runtime_logs` | `runtime-logs` | Yes | Yes |

## Real-data and placeholder pages

- Market Monitor reads the existing Market Snapshot service. Investment Watchlist data is kept separate from the
  Strategy Watchlist. User aggregation is empty until a reliable multi-user event source exists.
- Strategy Scoreboard reads existing system Trade Reviews and uses saved outcomes for counts and win rate. Return,
  Profit Factor, MFE/MAE averages and holding aggregates show `—` when not calculated by the data layer.
- System Monitor uses existing Platform Health, Runtime and Dashboard Summary services. It does not claim that
  OpenD, Telegram, AI or workers are connected when they are stopped or unconfigured.
- Runtime Logs only shows persisted service error summaries. It never accepts filesystem paths or exposes stacks,
  environment variables or secrets.
- Paper Positions, Parameter Comparison, User Behavior, Bot Statistics and User Intelligence are honest product
  placeholders with their final field structures. User Position and Portfolio Holding are never presented as Paper
  Positions.
- User Feedback reuses Development Issues with `source_type=USER_FEEDBACK`; no separate schema was added.

## Workbench, Sidebar and button audit

The Workbench uses six compact KPIs, a three-column operational row and a two-column strategy/product row. Loading
and failure states are explicit, with a safe retry action. Sidebar groups are independently collapsible and persisted
in local storage. The global compact Sidebar state remains available. Disabled controls have a reason tooltip and do
not issue requests; the shell contains no `href="#"` links.

## Telegram brand preparation

Five Bot aliases are defined by the centralized Profile model. Every alias declares purpose, language, market scope,
display name, descriptions, commands, menus, final `/start` copy, profile asset and explicit enable flag. Profiles are
disabled by default and safe summaries expose only whether a Token is configured. `/start` is text plus buttons and
does **not** place an image at the top.

`scripts/sync_telegram_profiles.py --all` is dry-run by default. It prepares `getMe`, `setMyName`, descriptions,
commands and command menu synchronization. Bot profile-photo upload is accurately marked `MANUAL_REQUIRED`, because
Telegram Bot API has no method to update a bot avatar; Windows deployment must use BotFather. Part D performs no
Telegram request, sends no message, and starts no Polling or Webhook.

## Logo tracking

- Official English asset: `app/dashboard/static/branding/trade-companion-logo.png`
- Login, Sidebar, favicon, Version Center, README and Telegram profile configuration reuse this asset.
- Telegram avatar upload remains a manual BotFather operation; the sync tool does not upload it.

## Screenshot paths

Automated route rendering is verified through FastAPI TestClient. The managed Mac execution sandbox blocked local
socket binding with `operation not permitted`, and Terminal UI control was also denied, so fresh-process browser
screenshots could not be generated in this run. No screenshot is fabricated. Windows handoff should capture the
listed pages after starting the current commit and confirming HTTP 200 responses.

## Boundaries and Windows-only items

No schema, Migration, API contract, Strategy/Feature/Candidate/Trade Plan/Review/AI business logic, OpenD logic or
Telegram Runtime was changed. Windows remains responsible for Token rotation, real Bot profile synchronization,
BotFather avatar setup, Runtime start and command/callback validation.
