# Trade Companion 1.0.0-rc2 Release Checklist

## Environment

- [ ] Python is 3.9.x and virtual environment is active.
- [ ] `python scripts/check_environment.py` passes.
- [ ] `python -m pip check` reports no conflicts.
- [ ] `.env` exists locally, is not tracked, and all optional runtimes are intentionally configured.
- [ ] Free disk space exceeds configured warning and minimum thresholds.

## Database and backup

- [ ] Verified backup exists before migration or deployment.
- [ ] `alembic current` and `alembic heads` both report `0019`.
- [ ] Core record counts are captured before and after deployment.
- [ ] SQLite path is writable only by the application operator.

## Dashboard and API

- [ ] Dashboard login, overview, empty states and navigation load.
- [ ] `/health`, `/docs`, Snapshot, Symbol Overview, Portfolio and Review APIs respond.
- [ ] Internal endpoints are absent from OpenAPI and require administrator authentication.
- [ ] API responses do not contain secrets or stack traces.

## AI and Telegram product layer

- [ ] AI Companion Mock/dry-run works without external network requests.
- [ ] Telegram Preview returns `preview=true` and `sent=false`.
- [ ] No Telegram Runtime, Polling, Webhook or real send is claimed for this RC.

## Quality, documentation and Git

- [ ] Full offline regression, compileall and pip check pass.
- [ ] Live OpenD tests are either explicitly executed against a logged-in OpenD or recorded as unavailable.
- [ ] Installation, deployment, backup and known-issues documents are current.
- [ ] Version reports Trade Companion 1.0.0-rc2 / Sprint 40 / Migration 0019.
- [ ] Working tree is clean; commit is reviewed; no `.env`, database, logs or secrets are staged.
