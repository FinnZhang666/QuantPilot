# Trade Companion Windows Service Plan

This release provides auditable process entry points but does not register Windows services or Scheduled Tasks.

## Fixed paths

- Project working directory: the repository root resolved from each script location.
- Python: `.venv\Scripts\python.exe` under the repository root.
- Environment: `.env` under the repository root; it is never copied or printed.
- Formal database: `E:\QuantPilotData\quantpilot.db`, configured only in local `.env`.
- PID and process logs: `.runtime\pids` and `.runtime\logs`; both are ignored by Git.

## Components

- `api`: Dashboard/API only; Paper and Telegram autostart are forced off in this process.
- `runtime`: the single Paper Runtime Manager worker; it refuses to start unless explicitly enabled in `.env`.
- `telegram`: the single Telegram Runtime worker; only the production Bot is enabled by the registry.

## Manual operations

```powershell
.\scripts\windows\start-trade-companion.ps1 -Component api
.\scripts\windows\start-trade-companion.ps1 -Component runtime
.\scripts\windows\start-trade-companion.ps1 -Component telegram

.\scripts\windows\stop-trade-companion.ps1 -Component telegram
.\scripts\windows\restart-trade-companion.ps1 -Component api
```

The stop script verifies that a PID still belongs to the expected entry point before stopping it. A stale or reused PID is never stopped blindly.

## Future service registration

After storage expansion and Beta observation, an administrator may map the three entry points to NSSM or Windows Task Scheduler with automatic restart and bounded retry. Registration must be an explicit maintenance action. This repository does not modify Windows startup settings automatically.
