import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.database.models import SystemPaperSchedulerJob
from app.paper_runtime.audit import PaperAudit
from app.paper_runtime.performance import PaperPerformanceService
from app.paper_runtime.review import SystemPaperReviewService
from app.paper_runtime.service import PaperTradingService


class PaperScheduler:
    """Non-overlapping coordinator. Jobs call services and contain no trading rules."""

    JOB_KEYS = (
        "market_data_refresh", "feature_incremental", "candidate_scan",
        "trade_plan_generation", "paper_entry_evaluation", "exit_evaluation",
        "position_valuation", "review_generation", "scoreboard_refresh",
        "equity_snapshot", "paper_trade_notifications",
    )

    def __init__(self, settings, session_factory, notification_callback=None):
        self.settings = settings
        self.session_factory = session_factory
        self.notification_callback = notification_callback
        self._run_lock = threading.Lock()
        self.current_task: Optional[str] = None

    def run_once(self, dry_run: bool = False, max_entries: Optional[int] = None):
        if dry_run:
            db = self.session_factory()
            try:
                return PaperTradingService(db, self.settings).dry_run(max_entries=max_entries)
            finally:
                db.close()
        if not self._run_lock.acquire(blocking=False):
            return {"status": "BUSY", "reason": "Scheduler run already in progress"}
        try:
            results: Dict[str, object] = {}
            jobs = (
                ("market_data_refresh", None),
                ("feature_incremental", None),
                ("candidate_scan", None),
                ("trade_plan_generation", None),
                ("paper_entry_evaluation", lambda: self._paper_entries(max_entries)),
                ("exit_evaluation", self._paper_exits),
                ("position_valuation", self._position_valuation),
                ("review_generation", self._reviews),
                ("scoreboard_refresh", self._scoreboard),
                ("equity_snapshot", self._equity_snapshot),
                ("paper_trade_notifications", self._notifications),
            )
            for job_key, callback in jobs:
                self.current_task = job_key
                if callback is None:
                    result = {
                        "status": "SAFE_DISABLED",
                        "reason": "External realtime pipeline remains disabled in Windows Phase 4",
                    }
                    self._save_job(job_key, result, 0, enabled=False)
                else:
                    result = self._run_job(job_key, callback)
                results[job_key] = result
            return {"status": "SUCCESS", "dry_run": False, "jobs": results}
        finally:
            self.current_task = None
            self._run_lock.release()

    def status(self):
        db = self.session_factory()
        try:
            rows = list(db.scalars(select(SystemPaperSchedulerJob).order_by(
                SystemPaperSchedulerJob.job_key,
            )))
            return {
                "enabled": self.settings.paper_scheduler_enabled,
                "non_overlapping": True,
                "current_task": self.current_task,
                "jobs": [self._serialize(row) for row in rows],
            }
        finally:
            db.close()

    def _run_job(self, job_key: str, callback: Callable[[], Dict[str, object]]):
        started = time.perf_counter()
        try:
            result = self._with_sqlite_retry(callback)
            duration = int((time.perf_counter() - started) * 1000)
            self._save_job(job_key, result, duration, enabled=True)
            return result
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            result = {"status": "FAILED", "error": type(exc).__name__}
            self._save_job(job_key, result, duration, enabled=True, error=type(exc).__name__)
            raise

    def _with_sqlite_retry(self, callback):
        retries = self.settings.paper_trading_sqlite_lock_retries
        for attempt in range(retries + 1):
            try:
                return callback()
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt >= retries:
                    raise
                time.sleep(self.settings.paper_trading_sqlite_lock_backoff_seconds * (2 ** attempt))

    def _paper_entries(self, max_entries):
        if not self.settings.paper_trading_enabled:
            return {"status": "DISABLED", "opened": 0, "waiting": 0, "rejected": 0}
        db = self.session_factory()
        try:
            service = PaperTradingService(db, self.settings)
            account = service.account()
            result = service.evaluate_entries(account, max_entries=max_entries)
            service.value_account(account, source="ENTRY_EVALUATION")
            db.commit()
            return {"status": "SUCCESS", **result}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _paper_exits(self):
        if not self.settings.paper_trading_enabled:
            return {"status": "DISABLED", "closed": 0, "partial": 0}
        db = self.session_factory()
        try:
            service = PaperTradingService(db, self.settings)
            account = service.account()
            result = service.evaluate_exits(account)
            service.value_account(account, source="EXIT_EVALUATION")
            db.commit()
            return {"status": "SUCCESS", **result}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _position_valuation(self):
        if not self.settings.paper_trading_enabled:
            return {"status": "DISABLED"}
        db = self.session_factory()
        try:
            service = PaperTradingService(db, self.settings)
            account = service.account()
            service.value_account(account, source="POSITION_VALUATION")
            db.commit()
            return {"status": "SUCCESS", "equity": str(account.total_equity)}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _reviews(self):
        if not self.settings.review_runtime_enabled:
            return {"status": "DISABLED", "created": 0}
        db = self.session_factory()
        try:
            return SystemPaperReviewService(db).generate_pending(limit=100)
        finally:
            db.close()

    def _scoreboard(self):
        if not self.settings.strategy_scoreboard_enabled:
            return {"status": "DISABLED", "strategies": 0}
        db = self.session_factory()
        try:
            items = PaperPerformanceService(db).scoreboard()
            PaperAudit(db).record(
                "SCOREBOARD_UPDATED", details={"strategies": len(items)},
            )
            db.commit()
            return {"status": "SUCCESS", "strategies": len(items)}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _equity_snapshot(self):
        if not self.settings.paper_trading_enabled:
            return {"status": "DISABLED"}
        db = self.session_factory()
        try:
            service = PaperTradingService(db, self.settings)
            account = service.account()
            service.value_account(account, source="EQUITY_SNAPSHOT")
            db.commit()
            return {"status": "SUCCESS", "equity": str(account.total_equity)}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _notifications(self):
        if self.notification_callback is None:
            return {"status": "DISABLED", "sent": 0, "skipped": 0, "failed": 0}
        return self.notification_callback()

    def _save_job(self, job_key, result, duration_ms, enabled, error=None):
        db = self.session_factory()
        try:
            row = db.scalar(select(SystemPaperSchedulerJob).where(
                SystemPaperSchedulerJob.job_key == job_key,
            ))
            if row is None:
                row = SystemPaperSchedulerJob(job_key=job_key)
                db.add(row)
            now = datetime.now(timezone.utc)
            row.enabled = enabled
            row.status = str(result.get("status", "UNKNOWN"))
            row.last_run_at = now
            row.next_run_at = (
                now + timedelta(seconds=self.settings.paper_trading_poll_seconds)
                if self.settings.paper_scheduler_enabled and enabled else None
            )
            row.duration_ms = duration_ms
            row.result_json = result
            row.last_error = error
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _serialize(row):
        return {
            "job_key": row.job_key, "enabled": row.enabled, "status": row.status,
            "last_run_at": row.last_run_at, "next_run_at": row.next_run_at,
            "duration_ms": row.duration_ms, "result": row.result_json,
            "last_error": row.last_error,
        }
