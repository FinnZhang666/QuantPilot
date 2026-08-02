# Trade Companion v1.0.0 Beta

Release tag: `v1.0.0-beta.1`  
Stage: Beta Draft / Pre-release  
Migration Head: `0024`

## Core

- Market Data is stored once and updated incrementally for shared use by Feature Engine, Strategy Engine and research workflows.
- Feature Engine and Feature cache support repeatable Candidate Signals without changing existing strategy formulas or thresholds.
- Candidate Signals flow into Trade Plans; a Trade Plan may correctly remain unavailable when deterministic gates do not pass.

## Paper Trading

- Paper Trading Only: Paper Account, Paper Orders, Paper Fills and Paper Positions are isolated from user and broker positions.
- Entry / Exit Engine uses versioned, deterministic and conservative fill rules.
- Equity Curve, realized and unrealized P/L, drawdown, MFE and MAE are derived from system data.
- Trade Review preserves immutable context and versions; Strategy Scoreboard reports system paper results only.

## Product

- Dashboard provides Market Snapshot, Symbol Overview, Trade Plans, positions, reviews, scoreboards and runtime status.
- AI Companion uses Gemini structured context and safe Telegram HTML rendering.
- Telegram Runtime uses a Single Bot Multi-language flow with persistent Chinese/English selection; four additional Bots remain Reserved.
- User Feedback and Admin Notifications are stored and auditable, including multi-administrator delivery.

## Platform

- Windows Compatibility is verified as the primary runtime while Python 3.9 and cross-platform paths remain supported.
- Runtime Manager coordinates lifecycle and preserves idempotency; Public ReadOnly Dashboard APIs remain separated from authenticated internal mutations.
- OpenAPI, Version Center, Dashboard footer and browser metadata share version `1.0.0-beta.1`.
- Migration Head 0024 is the current Database Migration Head.

## Gemini integration

- Real Gemini-to-Telegram delivery has been validated with no Markdown-star leakage.
- Timeout and provider failures degrade safely and do not crash the Bot runtime.

## Security boundaries

- No Real Broker Orders.
- No Real Position Sync.
- OpenD is market-data only; Broker writes remain disabled.
- Secrets stay in local `.env`; databases, logs and backups are excluded from Git.
- Credentials exposed during development must be rotated before formal Beta operation.

## Known limitations

- Strategy samples are still small and do not establish long-term profitability.
- Trade Plan count may currently be zero.
- Sharpe does not yet have a reliable sample and is intentionally not claimed.
- Telegram Bot avatar must be set manually through BotFather.
- Long-term operational stability requires Beta observation; no 30-day stability validation is claimed.
- Full restore rehearsal is pending storage expansion.

This release does not guarantee profit, does not claim long-term return validation and does not provide automated real-money trading.
