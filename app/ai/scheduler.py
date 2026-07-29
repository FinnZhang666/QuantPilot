import threading
from datetime import datetime, timezone

from app.ai.service import AIReviewService
from app.database.session import get_session_factory
from app.runtime.runtime_state import RuntimeStateRepository


class AIReviewScheduler:
    def __init__(self, settings, session_factory=None):
        self.settings = settings
        self.session_factory = session_factory or get_session_factory()
        self.thread = None
        self.lock = threading.Lock()
        self.last_run_at = None

    def trigger(self):
        if not self.settings.ai_review_enabled or not self.settings.ai_review_auto_run:
            return False
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            self.thread = threading.Thread(
                target=self._run, name="ai-review-analyst", daemon=True,
            )
            self.thread.start()
            return True

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=min(5, self.settings.ai_review_timeout_seconds))

    def _run(self):
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update("ai_review_analyst", "RUNNING")
            result = AIReviewService(db, self.settings).run(
                limit=self.settings.ai_review_batch_size,
            )
            RuntimeStateRepository(db).update(
                "ai_review_analyst", "CONNECTED", success=True, metadata=result,
            )
        except Exception as exc:
            db.rollback()
            RuntimeStateRepository(db).update(
                "ai_review_analyst", "DEGRADED",
                error=type(exc).__name__ + "：AI Review后台任务失败。",
            )
        finally:
            self.last_run_at = datetime.now(timezone.utc)
            db.close()
