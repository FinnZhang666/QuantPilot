import logging
import threading
from datetime import datetime, timedelta, timezone

from app.database.session import get_session_factory
from app.universe.service import UniverseService
from app.qmr.service import QmrService
from app.recovery.service import RecoveryService
from app.buy_score.service import BuyScoreService
from app.qmr_live.service import QmrLiveSignalService
from app.qmr_live.tracking import QmrPerformanceTracker

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
                    if self.settings.qmr_enabled and self.settings.qmr_auto_update_enabled:
                        qmr = QmrService(db, self.settings)
                        latest_qmr = qmr.repository.latest_evaluation_time()
                        if latest_qmr is None or datetime.now(timezone.utc) - latest_qmr >= timedelta(minutes=self.settings.qmr_update_interval_minutes):
                            qmr.run(limit=1000)
                    if self.settings.recovery_enabled and self.settings.recovery_auto_update_enabled:
                        recovery = RecoveryService(db, self.settings)
                        latest_recovery = recovery.repository.latest_evaluation_time()
                        if latest_recovery is None or datetime.now(timezone.utc) - latest_recovery >= timedelta(minutes=self.settings.recovery_update_interval_minutes):
                            recovery.run(limit=1000)
                    if self.settings.buy_score_enabled and self.settings.buy_score_auto_update_enabled:
                        buy_score = BuyScoreService(db, self.settings)
                        latest_buy_score = buy_score.repository.latest_evaluation_time()
                        if latest_buy_score is None or datetime.now(timezone.utc) - latest_buy_score >= timedelta(minutes=self.settings.recovery_update_interval_minutes):
                            buy_score.run(limit=1000)
                    if self.settings.qmr_live_enabled:
                        QmrLiveSignalService(db, self.settings).run()
                        QmrPerformanceTracker(db, self.settings).run()
            except Exception:
                logger.exception("Scheduled Universe update failed")
            interval = self.settings.recovery_update_interval_minutes * 60 if self.settings.recovery_auto_update_enabled else 3600
            self._stop.wait(min(3600, interval))


_scheduler = None


def get_universe_scheduler(settings):
    global _scheduler
    if _scheduler is None:
        _scheduler = UniverseScheduler(settings)
    return _scheduler
