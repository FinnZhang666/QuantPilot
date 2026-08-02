# Trade Companion Deployment

## Release boundary

This guide covers the macOS/POSIX FastAPI application with SQLite. It does not cover Windows deployment,
OpenD runtime operation, Telegram polling/webhooks, Broker integration, workers, or schedulers.

## Development

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Use an isolated database and keep all optional runtimes disabled. `--reload` is development-only.

## Production candidate

1. Create a dedicated OS user and writable `data/`, `logs/`, and `backups/` directories.
2. Install the locked-compatible requirements in a Python 3.9 virtual environment.
3. Copy `.env.example` to a protected `.env`; set a strong Dashboard token and an explicit database path.
4. Keep live trading and order submission disabled.
5. Create and verify a backup, then run `alembic upgrade head`.
6. Run the release checklist and start one application process:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

SQLite and in-process runtime state require a single worker. Put a local TLS reverse proxy in front only when
remote access is required, restrict it to a trusted network, and never expose internal endpoints publicly.

## Operations

```bash
python -m app.cli health
python -m app.cli version
python -m app.cli backup create --type daily
python -m app.cli backup verify
```

Monitor rotating logs without logging `.env` or request authorization headers. Stop the application cleanly before
filesystem maintenance. Roll back code only together with a database backup compatible with its Alembic revision.

## Disabled integrations

External AI Provider, Telegram Runtime, OpenD Runtime and Broker execution remain deployment-specific and disabled
for this RC. Enabling them is not part of this guide and must not be inferred from successful Preview/API tests.

## Telegram Bot Profile Synchronization (Windows handoff)

The Mac handoff includes five disabled, alias-based Bot Profiles, localized copy, commands, menus and a 512×512
profile asset. `/start` uses text and buttons only; it does not send a welcome image.

1. Rotate every Token previously shared outside the protected deployment environment.
2. Store the replacement values only in the Windows `.env`, using the documented alias variables.
3. Run `python scripts/sync_telegram_profiles.py --all` and inspect the dry-run report.
4. Check each alias, intended language, market scope and explicit enabled flag.
5. Apply supported profile fields one Bot at a time with `--bot ALIAS --apply` only after approval.
6. Set the profile photo manually through BotFather using the official English asset
   `app/dashboard/static/branding/trade-companion-logo.png`; Bot API cannot upload it.
7. Start the Telegram Runtime only after profile synchronization and environment validation.
8. Test `/start`, localized Commands, the four-item menu and every Callback.
9. Validate administrator feedback notifications without exposing ordinary user details.
10. Confirm `.env`, Tokens and sync logs containing sensitive data are absent from Git.

The synchronization tool is dry-run by default. `--apply` performs real Telegram API requests and is reserved for
the Windows deployment stage.

## Paper Trading Dashboard KPI (Windows runtime handoff)

After the audited Paper Trading Runtime is implemented and validated on Windows, the administrator Dashboard
represents the system account by default. Its primary KPIs must be Total Equity, Today's P/L, Total Return,
Positions, Win Rate and Runtime status. The Portfolio view must derive cash, position market value, realized and
unrealized P/L, and total return exclusively from Paper Positions plus the latest stored market data. It must never
substitute Broker Positions, User Positions or users' real accounts.

The intended runtime chain is OpenD read-only market data → Feature Engine → Strategy Engine → Candidate → Trade
Plan → Paper Trading Runtime → Paper Position → automated paper exits → Trade Review → Strategy Scoreboard → AI
Review. This future runtime remains paper-only and must never submit a real broker order. The Dashboard should also
add an Equity Curve sourced from system-account equity history. Until those sources exist, the UI must display an
honest unavailable state instead of sample balances, returns or positions.
