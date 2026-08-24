import logging
import threading
from datetime import datetime, timedelta, timezone

from app.database.session import get_session_factory
from app.universe.service import UniverseService

logger = logging.getLogger("trade_companion.universe.scheduler")


class UniverseScheduler:
    def __init__(self, settings):
        self.settings = settings
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="universe-updater", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while not self._stop.is_set():
            try:
                with get_session_factory()() as db:
                    service = UniverseService(db, self.settings)
                    latest = service.repository.latest_success_at()
                    if latest is None or datetime.now(timezone.utc) - latest >= timedelta(hours=self.settings.universe_update_interval_hours):
                        service.update()
            except Exception:
                logger.exception("Scheduled Universe update failed")
            self._stop.wait(3600)


_scheduler = None


def get_universe_scheduler(settings):
    global _scheduler
    if _scheduler is None:
        _scheduler = UniverseScheduler(settings)
    return _scheduler
