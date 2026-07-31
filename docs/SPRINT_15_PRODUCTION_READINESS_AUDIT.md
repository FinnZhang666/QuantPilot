# Sprint 15 Production Readiness Audit

## 1. Summary

This audit reviewed the current Trade Companion repository without changing trading
logic, API contracts, database schema, scheduling frequencies, Telegram command
flows, branding, or UI. No migration was created and the existing database was
opened read-only for production-data checks.

The only code changes are reliability improvements with unchanged functional
results:

- backup SHA-256 verification now streams bounded chunks instead of loading a
  multi-gigabyte archive into memory;
- the Telegram command polling thread degrades and retries after an unexpected
  iteration failure instead of terminating silently;
- non-critical Research synchronization failures remain isolated from the main
  Opportunity, Review, and AI Review flows, but are now logged.

## 2. Issues found

### Addressed

1. `BackupService.verify()` used `Path.read_bytes()`. Backup files can be close
   to the database size, so verification could temporarily allocate several
   gigabytes and be terminated by the operating system.
2. `TelegramCommandPoller` handled HTTP and payload errors but an unexpected
   database/runtime exception could terminate its long-running thread.
3. Research synchronization is intentionally a side channel, but three failure
   paths rolled back silently and left no operational evidence.

### Recorded for future cleanup; not changed in this audit

1. FastAPI lifespan calls `Base.metadata.create_all()` during application
   startup. The `/health` implementation itself is read-only, but process
   startup still has initialization behavior. Replacing this with an explicit
   Alembic deployment gate requires a separately approved compatibility change.
2. The runtime PID file is stale while persisted runtime rows still report
   `RUNNING` or `CONNECTED`. Status reporting needs heartbeat-age/PID
   reconciliation instead of trusting the last stored status alone.
3. A static AST scan reported likely unused imports in production modules,
   including `app/ai/service.py`, several API modules, feature/history helpers,
   and strategy helpers. Re-export imports in package `__init__.py` files are
   intentional and must not be removed mechanically.
4. Several API modules catch broad `Exception` and convert `str(exc)` to a 400
   response. Narrowing these to declared domain exceptions would improve error
   classification and reduce the possibility of leaking internal details, but
   it may alter established error messages.
5. Multiple background services intentionally catch broad exceptions for fault
   isolation. Logging and error taxonomy are inconsistent between the realtime,
   review, AI, historical, and candidate-pool modules.
6. CLI `print()` calls are user-facing output and are appropriate. No service
   layer `print()` calls were found. The CLI output and logger paths should remain
   distinct.
7. No active TODO/FIXME/debugger statements were found in application code.
8. A local `.DS_Store` exists but is not tracked. It should remain excluded;
   automatic deletion was intentionally not performed.
9. Legacy execution abstractions remain in the repository. Safety tests cover
   their blocked/live-disabled behavior; this audit did not remove or reorganize
   them.

## 3. Configuration and secret audit

- Runtime modules use the centralized Settings entry point. Direct environment
  writes were found only in an isolated Dashboard smoke-test process.
- `.env`, SQLite databases, logs, and PID files are ignored by Git.
- No Telegram-token-shaped credential was found in tracked files.
- `/health`, platform configuration output, and logging sanitization retain
  secret masking. No secret value is included in this report.
- The repository contains no hard-coded macOS `/Users/...` path in application,
  scripts, or documentation.

## 4. API, scheduler, Telegram, and database audit

- API request/response models and routes were not modified.
- Scheduler frequencies and trigger rules were not modified.
- Telegram commands, menus, callbacks, and conversation flow were not modified.
- SQLAlchemy request sessions close in generator `finally` blocks; inspected
  background tasks also close their independently created sessions in `finally`.
- No table, index, SQL structure, Alembic file, or persisted production record
  was changed as part of the audit.
- The health endpoint performs availability queries and diagnostics only. It
  does not migrate, reconnect OpenD, or start a runtime service.

## 5. Verification results

- Python: 3.9.6.
- Full pytest: 534 passed, 2 skipped, 5 third-party deprecation warnings.
- Targeted Sprint 15 regression tests: passed.
- `compileall`: passed with an isolated temporary bytecode cache.
- `pip check`: no broken requirements.
- Git diff whitespace validation: passed.
- SQLite read-only connection: passed; 48 tables; Alembic revision 0014.
- Existing database size at audit time: 3,335,884,800 bytes.
- Free disk at audit time: 43,719,970,816 bytes (about 40.72 GiB).
- API and Dashboard startup/routes: verified by the full isolated integration
  suite. A real-database server was deliberately not started because existing
  application lifespan calls `create_all()`.
- Scheduler behavior: verified through automated tests; no persistent scheduler
  was started during the audit.
- OpenD: TCP availability check failed at the configured host and port. Login
  and market-data calls were therefore not verified.
- Runtime: the PID file was stale. Persisted status rows had last heartbeats from
  2026-07-29 and were not treated as current proof of service availability.
- Telegram: persisted status was from 2026-07-29. No live test message was sent,
  so current Bot API connectivity was not claimed.

## 6. Files recommended for future cleanup

- `app/main.py`: separate schema deployment from application startup after a
  compatibility plan is approved.
- `app/api/watchlist.py` and other broad exception adapters: establish typed
  domain errors and a safe global error response policy.
- `app/runtime/runtime_state.py` and runtime status APIs: add staleness and PID
  reconciliation.
- Production modules listed by the AST unused-import scan: confirm with an
  approved linter before removing individual imports.
- Duplicate legacy CLI scripts versus the unified `python -m app.cli` entry
  point: document deprecation before any removal.

## 7. Remaining risks and suggested next priorities

1. Make process health distinguish stored historical state from current liveness.
2. Remove schema initialization from web startup only after tests and deployment
   are migrated to an explicit Alembic bootstrap.
3. Introduce typed service exceptions and safe API error translation without
   changing response contracts.
4. Add supervised process management and a read-only liveness probe for Runtime,
   OpenD, Telegram polling, and schedulers.
5. Adopt an audit-only linter configuration first; do not run repository-wide
   autofix.

## 8. Scope confirmation

No business logic, branding, UI, public API contract, database schema, scheduler
frequency, Telegram command, package version, or project structure was changed.
No database was created, recreated, deleted, migrated, or populated. No history
download, order submission, or Git push was performed.
