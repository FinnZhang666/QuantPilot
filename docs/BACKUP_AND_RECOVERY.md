# Trade Companion Backup and Recovery

## Create and verify

The built-in backup uses SQLite's online backup API and packages the database, safe configuration templates and a
manifest into a ZIP file. It never includes `.env`.

```bash
python -m app.cli backup create --type manual
python -m app.cli backup list
python -m app.cli backup verify
```

Daily and weekly backups use `--type daily` and `--type weekly`; retention defaults to 7 daily and 4 weekly files.
Copy verified archives to separate storage manually. Cloud upload is not implemented.

## What to preserve separately

- Verified backup ZIP and its SHA-256 output
- The exact Git commit and Alembic revision
- A separately secured copy of local `.env` (never put it inside the repository or normal support bundles)
- Custom non-secret configuration and research attachments

## Restore

1. Stop FastAPI and all local runtimes; confirm no process is writing SQLite.
2. Preserve the failed database and current `.env` under a new name.
3. Verify the chosen ZIP with `python -m app.cli backup verify --path <archive>`.
4. Extract `database/quantpilot.db` into a temporary directory.
5. Confirm the application commit supports the backup's migration revision.
6. Move the restored database to the configured `DATABASE_URL` path using an explicit, reviewed filesystem action.
7. Run `alembic current`, `python -m app.cli health`, and read-only smoke tests before starting runtime services.

Never restore over a running database, never mix partial table exports, and never claim recovery until record counts
and application health have been verified.
