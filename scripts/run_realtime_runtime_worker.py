"""Single-process Windows worker for realtime data and opportunity processing."""

import json
import os
import signal
import threading
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.platform.process import process_exists
from app.runtime.realtime_runtime import get_runtime


PID_PATH = Path(__file__).resolve().parents[1] / "data" / "opportunity_runtime.pid"


def _claim_pid() -> None:
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PID_PATH.exists():
        try:
            payload = json.loads(PID_PATH.read_text(encoding="utf-8"))
            pid = int(payload.get("pid", 0))
            if pid and process_exists(pid):
                raise SystemExit("Realtime opportunity worker is already running")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        PID_PATH.unlink(missing_ok=True)
    PID_PATH.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")


def main() -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level, settings.log_directory,
        settings.log_max_bytes, settings.log_backup_count,
    )
    if not settings.realtime_runtime_enabled:
        raise SystemExit("Realtime worker is disabled: REALTIME_RUNTIME_ENABLED=false")

    _claim_pid()
    runtime = get_runtime(settings)
    stopped = threading.Event()

    def request_stop(_signum, _frame):
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        result = runtime.start()
        if result.get("status") not in {"RUNNING", "DEGRADED"}:
            raise SystemExit("Realtime worker failed to start: %s" % result.get("status"))
        while not stopped.wait(1):
            pass
    finally:
        runtime.stop()
        try:
            payload = json.loads(PID_PATH.read_text(encoding="utf-8"))
            if int(payload.get("pid", 0)) == os.getpid():
                PID_PATH.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass


if __name__ == "__main__":
    main()
