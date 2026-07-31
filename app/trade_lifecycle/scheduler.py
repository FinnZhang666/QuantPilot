import threading
from datetime import datetime, timezone

from app.database.session import get_session_factory
from app.runtime.runtime_state import RuntimeStateRepository
from app.trade_lifecycle.runtime import TradePlanRuntime


class TradePlanGeneratorScheduler:
    """Lightweight, non-overlapping scheduler triggered by the existing runtime loop."""

    def __init__(self, session_factory=None, batch_size: int = 100):
        self.session_factory = session_factory or get_session_factory()
        self.batch_size = batch_size
        self.thread = None
        self.lock = threading.Lock()
        self.last_run_at = None

    def trigger(self) -> bool:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            self.thread = threading.Thread(
                target=self._run, name="trade-plan-generator", daemon=True,
            )
            self.thread.start()
            return True

    def stop(self) -> None:
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

    def _run(self) -> None:
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update("trade_plan_generator", "RUNNING")
            result = TradePlanRuntime(db).run(self.batch_size)
            RuntimeStateRepository(db).update(
                "trade_plan_generator",
                "CONNECTED" if not result["errors_count"] else "DEGRADED",
                success=not result["errors_count"], metadata=result,
            )
        except Exception as exc:
            db.rollback()
            RuntimeStateRepository(db).update(
                "trade_plan_generator", "DEGRADED",
                error=type(exc).__name__ + "：" + str(exc),
            )
        finally:
            self.last_run_at = datetime.now(timezone.utc)
            db.close()
