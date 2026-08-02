# Trade Companion v1.0.0-beta.1 Release Checklist

## Release identity

- [ ] Product reports `Trade Companion`.
- [ ] Version Center, OpenAPI, Dashboard footer and browser metadata report `1.0.0-beta.1`.
- [ ] Alembic current and application health report Migration Head `0024`.
- [ ] The release is a GitHub Draft and Pre-release; it is not published as stable `v1.0.0`.

## Environment and Git

- [ ] Windows uses Python 3.9.x and the project virtual environment.
- [ ] `python -m pip check`, compileall and the full pytest suite pass.
- [ ] `origin` is `https://github.com/FinnZhang666/QuantPilot.git` and branch is `main`.
- [ ] Push dry-run succeeds; Ahead / Behind is `0 / 0`; the working tree is clean.
- [ ] `.env`, SQLite databases, backups, runtime logs and secrets are not tracked.

## Database, disk and recovery

- [ ] Dashboard, CLI and runtimes use `E:\QuantPilotData\quantpilot.db` only.
- [ ] `PRAGMA quick_check` reports `ok`; no VACUUM or full Feature rebuild is performed.
- [ ] Disk status follows: under 100GB WARNING, under 50GB CRITICAL, under 20GB EMERGENCY.
- [ ] Existing backup path and metadata are recorded without copying the active 130GB database.
- [ ] Restore rehearsal remains pending when storage is insufficient.

## Dashboard, API and runtime

- [ ] Dashboard pages, `/docs`, `/openapi.json` and public read-only endpoints return no 404 or 500.
- [ ] Browser console reports zero errors.
- [ ] Internal APIs stay outside OpenAPI and require administrator authentication.
- [ ] Runtime Manager, Paper Account and Run Once health checks pass without manufacturing trades.
- [ ] Real order calls, Broker writes and real position synchronization remain zero.

## Telegram and Gemini

- [ ] All five configured Bots run under one unified Runtime and report configured tokens.
- [ ] Profile Sync readback, `/start`, language selection, callbacks and Feedback pass UAT.
- [ ] Administrator notification and Gemini real delivery pass.
- [ ] Preview and real delivery use the same renderer; output has no raw `*` or `#` leakage.
- [ ] Watchlist symbol addition, batch analysis and contextual AI follow-up pass.
- [ ] User-visible output contains Trade Companion branding, not the compatibility name QuantPilot.
- [ ] The Bot avatar remains a manual BotFather step.

## Beta boundaries

- [ ] Release Notes explicitly state Paper Trading Only and No Real Broker Orders.
- [ ] Notes disclose limited strategy samples, possibly zero Trade Plans, unavailable reliable Sharpe and pending long-term observation.
- [ ] Previously exposed Telegram and Gemini credentials are rotated before public Beta operation.
