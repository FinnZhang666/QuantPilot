import threading
from datetime import datetime, timezone
from typing import Optional

from app.core.config import Settings, get_settings
from app.database.session import get_session_factory
from app.paper_runtime.service import PaperTradingService
from app.runtime.runtime_state import RuntimeStateRepository
from app.trade_review.runtime import TradeReviewRuntime


class PaperTradingRuntime:
    def __init__(self, settings, session_factory):
        self.settings, self.session_factory = settings, session_factory

    def process_once(self):
        db = self.session_factory()
        try:
            return PaperTradingService(db, self.settings).process_once()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


class ReviewRuntime:
    def __init__(self, settings, session_factory):
        self.settings, self.session_factory = settings, session_factory

    def process_once(self):
        if not self.settings.review_runtime_enabled:
            return {"status": "DISABLED", "created": 0}
        db = self.session_factory()
        try:
            return TradeReviewRuntime(db).generate_reviews(dry_run=False, limit=100)
        finally:
            db.close()


class StatisticsRuntime:
    def __init__(self, settings, session_factory):
        self.settings, self.session_factory = settings, session_factory

    def process_once(self):
        if not self.settings.strategy_scoreboard_enabled:
            return {"status": "DISABLED"}
        db = self.session_factory()
        try:
            account = PaperTradingService(db, self.settings).account()
            PaperTradingService(db, self.settings).value_account(account)
            db.commit()
            return {"status": "SUCCESS", "equity": str(account.total_equity)}
        finally:
            db.close()


class RuntimeManager:
    """Lifecycle coordinator; business rules remain inside individual services."""

    def __init__(self, settings: Optional[Settings] = None, session_factory=None):
        self.settings = settings or get_settings()
        self.session_factory = session_factory or get_session_factory()
        self.paper = PaperTradingRuntime(self.settings, self.session_factory)
        self.review = ReviewRuntime(self.settings, self.session_factory)
        self.statistics = StatisticsRuntime(self.settings, self.session_factory)
        self.stop_event = threading.Event()
        self.thread = None
        self.status = "STOPPED"
        self.last_run_at = None
        self.last_result = {}
        self.error_count = 0

    def start(self):
        if not self.settings.runtime_manager_enabled:
            return self.snapshot(disabled=True)
        if self.thread and self.thread.is_alive():
            return self.snapshot(idempotent=True)
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, name="paper-runtime-manager", daemon=True)
        self.status = "RUNNING"
        self.thread.start()
        self._save_state()
        return self.snapshot()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.status = "STOPPED"
        self._save_state()
        return self.snapshot()

    def process_once(self):
        if not self.settings.runtime_manager_enabled:
            return self.snapshot(disabled=True)
        result = {
            "paper": self.paper.process_once(),
            "review": self.review.process_once(),
            "statistics": self.statistics.process_once(),
        }
        self.last_result = result
        self.last_run_at = datetime.now(timezone.utc)
        self._save_state(success=True)
        return result

    def snapshot(self, **extra):
        return {
            "status": self.status,
            "enabled": self.settings.runtime_manager_enabled,
            "paper_trading_enabled": self.settings.paper_trading_enabled,
            "review_runtime_enabled": self.settings.review_runtime_enabled,
            "strategy_scoreboard_enabled": self.settings.strategy_scoreboard_enabled,
            "thread_alive": bool(self.thread and self.thread.is_alive()),
            "last_run_at": self.last_run_at,
            "last_result": self.last_result,
            "error_count": self.error_count,
            **extra,
        }

    def _loop(self):
        while not self.stop_event.wait(self.settings.paper_trading_poll_seconds):
            try:
                self.process_once()
            except Exception as exc:
                self.error_count += 1
                self.status = "DEGRADED"
                self._save_state(error=type(exc).__name__)

    def _save_state(self, error=None, success=False):
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update(
                "paper_runtime_manager", self.status,
                metadata={"last_result": self.last_result, "error_count": self.error_count},
                error=error, success=success,
            )
        finally:
            db.close()


_manager = None


def get_runtime_manager(settings=None):
    global _manager
    if _manager is None:
        _manager = RuntimeManager(settings)
    return _manager


def replace_runtime_manager(manager):
    global _manager
    _manager = manager
