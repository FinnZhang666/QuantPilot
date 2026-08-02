# Windows Phase 5: Telegram Runtime

## Scope

Phase 5 adds the Trade Companion Telegram product runtime. It reuses the existing
Telegram product profiles, formatters, FastAPI business services, Dashboard, and
database. It does not add another Bot management UI or another notification center.

## Architecture

```text
Unified Telegram Runtime
  -> configuration-backed Bot Registry
  -> shared update router
  -> Trade Companion services and repositories
  -> shared message renderer
  -> Telegram Bot API transport
```

One runtime thread polls the single production Bot. A Bot never starts its own
independent runtime. The same Bot persists each user's `zh-CN` or `en-US` choice and
renders every later interaction in that language. Bot tokens are resolved from local Settings and are never stored
in JSON, SQLite, logs, API responses, previews, or Git.

## Bot Registry

`config/telegram_bots.json` stores alias, language, public profile copy, commands,
menu, welcome template, runtime flag, and the Settings field that holds its token.
It contains no token. `trade_companion_ai` is the only production alias. Four other
profiles remain `RESERVED` for configuration/history compatibility and are not polled
or synchronized.

## Runtime lifecycle

The runtime supports `start`, `stop`, `run once`, status, persisted offsets, and
graceful process shutdown. Runtime and autostart remain independently controlled by:

- `TELEGRAM_ENABLED`
- `TELEGRAM_RUNTIME_ENABLED`
- `TELEGRAM_RUNTIME_AUTOSTART`

OpenD realtime, broker access, and real trading are not started by Telegram.

## Bot Sync

Sync supports dry run and apply. Apply updates and then reads back:

- Name
- About
- Description
- Commands
- Command menu button

The exact readback must match the registry. Avatar is always `MANUAL_REQUIRED`
because BotFather does not expose an avatar upload through the Bot API. Welcome and
language are registry/runtime properties and are audited locally.

## Product flows

The first `/start` creates or updates a Telegram runtime user and requires a language
selection. The choice survives runtime restarts. Later `/start` calls render the saved
welcome/menu directly, with a Change Language callback kept under More. Required
callbacks route to real backend data for AI analysis, portfolio, market snapshot,
watchlist, holding, history, reviews, help, updates, feedback, and about.

## AI Companion

The Gemini adapter supports stock analysis, position explanation, trade explanation,
strategy review, and market summary. It sends only selected business context. The
prompt prohibits recalculation or invention of numbers. Failure returns a deterministic
system-data fallback and records a redacted invocation audit. Automated tests inject a
fake transport and never consume Gemini quota.

Gemini text is passed through a shared HTML renderer. The renderer escapes all model
HTML, converts Markdown headings and lists to Telegram-safe HTML/Unicode, replaces
remaining asterisks with the mathematical star glyph, appends a fixed Trade Companion
disclaimer, and enforces Telegram's 4096-character limit. Preview and real delivery use
the same renderer.

## Feedback and administrator notifications

Feedback categories are `BUG`, `FEATURE`, `STRATEGY`, `HELPFUL`, and `NOT_HELPFUL`.
Records are stored in SQLite and shown by the Dashboard with search/status filters.
`@ADHD360` and `@Kevinchou8` are seeded without Telegram IDs. The first matching
`/start` binds the immutable Telegram user ID. Bound administrators receive feedback,
runtime-error, and AI-error notifications.

## Preview contract

Preview calls the same renderer used by real delivery. The API returns
`preview_equals_real=true`. Preview never reads or returns a token and never sends a
Telegram request.

## Windows operations

1. Put each token in its matching local `.env` field. Do not paste tokens into logs,
   documentation, tests, or Git.
2. Keep `TELEGRAM_RUNTIME_AUTOSTART=false` for the first validation.
3. Run an authenticated dry-run sync.
4. Run an apply sync and inspect exact remote readback.
5. Start the runtime and send `/start` to bind administrators.
6. Run one controlled message smoke test.

Never commit `.env`, databases, runtime logs, or Telegram credentials.

## Safety boundaries

- Broker and real-order calls: forbidden and absent.
- OpenD: no runtime start from this module.
- Avatar: manual BotFather action only.
- External AI: bounded output, redacted errors, deterministic fallback.
- Telegram retries: finite; authorization and schema errors are not retried.
- Tokens: Settings-only and never returned by APIs.

## Known limitations

- The production Bot without a locally configured token stays `TOKEN_MISSING` and cannot sync or run.
- Reserved Bots are intentionally not synchronized or started.
- Administrator notification delivery starts only after `/start` binds an ID.
- Long polling is a single-process Beta implementation; no multi-host leader election.
- Avatar must be updated manually in BotFather.

Phase 5 must stop after Telegram acceptance. It does not begin Phase 6.
