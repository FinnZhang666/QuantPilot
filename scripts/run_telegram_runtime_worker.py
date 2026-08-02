"""Single-process Windows worker for the production Telegram Bot Runtime."""

import signal
import threading

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.telegram_runtime.runtime import get_telegram_runtime


def main():
    settings = get_settings()
    configure_logging(
        settings.log_level, settings.log_directory,
        settings.log_max_bytes, settings.log_backup_count,
    )
    runtime = get_telegram_runtime(settings)
    stopped = threading.Event()

    def request_stop(_signum, _frame):
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    result = runtime.start()
    if result.get("status") != "RUNNING":
        raise SystemExit("Telegram worker failed to start: %s" % result.get("status"))
    try:
        while not stopped.wait(1):
            pass
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
