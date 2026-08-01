# Trade Companion Installation

## Requirements

- macOS or another POSIX development host
- CPython 3.9.x; supported range is `>=3.9,<3.10`
- `pip` and `venv`
- SQLite (bundled with Python)
- Moomoo OpenD is optional for offline installation and is not configured by this guide

Docker and `uv` are not required.

## Install

```bash
git clone https://github.com/FinnZhang666/QuantPilot.git
cd QuantPilot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python scripts/check_environment.py
python -m pip check
```

`requirements-dev.txt` includes Hatchling so a source checkout can build the package. Runtime dependency ranges
match `pyproject.toml`, including pandas and NumPy used by the Feature Engine.

The repository/package/database compatibility names remain `QuantPilot`, `quantpilot`, and `quantpilot.db`
until the dedicated repository migration release.

## Environment

`.env.example` is the complete configuration inventory and matches all Settings fields. Keep these defaults for
an offline installation:

```dotenv
DATABASE_URL=sqlite:///./data/quantpilot.db
DASHBOARD_READONLY_PUBLIC=false
MOOMOO_ENABLED=false
REALTIME_RUNTIME_ENABLED=false
AI_COMPANION_ENABLED=false
AI_COMPANION_PROVIDER=mock
TELEGRAM_ENABLED=false
MOOMOO_LIVE_TRADING_ENABLED=false
MOOMOO_ALLOW_ORDER_SUBMISSION=false
```

Set a strong local `DASHBOARD_ADMIN_TOKEN`. Never commit `.env`, Bot tokens, API keys, account identifiers,
or OpenD credentials.

## Database and Alembic

Back up an existing database before migration. For a fresh installation, create `data/` and run:

```bash
mkdir -p data
alembic upgrade head
alembic current
```

Windows Phase 4 Head is `0022`. Do not copy a live SQLite database while it is being written; use the backup
command described in `BACKUP_AND_RECOVERY.md`.

## Start Dashboard and API

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Dashboard: <http://127.0.0.1:8000/dashboard>
- OpenAPI: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/health>

## AI Companion and Telegram Product Layer

AI Companion defaults to the deterministic offline Mock Provider and does not make an external request while
disabled. Telegram Preview at `/dashboard/telegram-preview` is presentation only: it does not need a token and
never sends a message. External AI and real Telegram runtime validation are outside this release candidate.

## Verify

```bash
python -m app.cli version
python -m app.cli config
python -m app.cli health
python -m pytest -m "not live_moomoo"
python -m compileall app
```
