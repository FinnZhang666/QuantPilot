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
