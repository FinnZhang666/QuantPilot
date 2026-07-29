import threading
from datetime import datetime, timezone

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.review.service import OpportunityReviewService
from app.runtime.runtime_state import RuntimeStateRepository


class ReviewScheduler:
    def __init__(self, settings=None, session_factory=None):
        self.settings = settings or get_settings()
        self.session_factory = session_factory or get_session_factory()
        self.thread = None
        self.lock = threading.Lock()
        self.last_run_at = None

    def trigger(self):
        if not self.settings.opportunity_review_enabled:
            return False
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            now = datetime.now(timezone.utc)
            if self.last_run_at and (
                now - self.last_run_at
            ).total_seconds() < self.settings.opportunity_review_poll_seconds:
                return False
            self.thread = threading.Thread(target=self._run, name="opportunity-review", daemon=True)
            self.thread.start()
            return True

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

    def _run(self):
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update("opportunity_review", "RUNNING")
            result = OpportunityReviewService(db, self.settings).run()
            RuntimeStateRepository(db).update(
                "opportunity_review", "CONNECTED", success=True, metadata=result,
            )
        except Exception as exc:
            db.rollback()
            RuntimeStateRepository(db).update(
                "opportunity_review", "DEGRADED",
                error=type(exc).__name__ + "：" + str(exc),
            )
        finally:
            self.last_run_at = datetime.now(timezone.utc)
            db.close()
