"""Single-process Windows worker for the system Paper Trading Runtime Manager."""

import signal
import threading

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.paper_runtime.manager import get_runtime_manager


def main():
    settings = get_settings()
    configure_logging(
        settings.log_level, settings.log_directory,
        settings.log_max_bytes, settings.log_backup_count,
    )
    if not settings.runtime_manager_enabled:
        raise SystemExit("Runtime worker is disabled: RUNTIME_MANAGER_ENABLED=false")
    manager = get_runtime_manager(settings)
    stopped = threading.Event()

    def request_stop(_signum, _frame):
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    result = manager.start()
    if result.get("status") not in {"RUNNING", "DEGRADED"}:
        raise SystemExit("Runtime worker failed to start: %s" % result.get("status"))
    try:
        while not stopped.wait(1):
            pass
    finally:
        manager.stop()


if __name__ == "__main__":
    main()
