import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.database.models import SystemPaperRuntimeLock
from app.database.session import get_session_factory
from app.paper_runtime.audit import PaperAudit
from app.paper_runtime.scheduler import PaperScheduler
from app.runtime.runtime_state import RuntimeStateRepository


class RuntimeManager:
    """Windows-safe lifecycle coordinator; the Scheduler invokes business services."""

    VALID_STATES = {
        "STOPPED", "STARTING", "RUNNING", "DEGRADED", "STOPPING", "FAILED",
    }

    def __init__(self, settings: Optional[Settings] = None, session_factory=None):
        self.settings = settings or get_settings()
        self.session_factory = session_factory or get_session_factory()
        self.scheduler = PaperScheduler(self.settings, self.session_factory)
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.status = "STOPPED"
        self.last_run_at = None
        self.last_success_at = None
        self.last_failure_at = None
        self.last_result = {}
        self.last_error = None
        self.error_count = 0
        self.process_id = os.getpid()
        self.owner_id = "%s:%s" % (self.process_id, uuid.uuid4().hex)
        self._lifecycle_lock = threading.RLock()
        self._owns_db_lock = False

    def start(self):
        with self._lifecycle_lock:
            if not self.settings.runtime_manager_enabled:
                return self.snapshot(disabled=True)
            if self.thread and self.thread.is_alive():
                return self.snapshot(idempotent=True)
            self._set_status("STARTING")
            if not self._acquire_db_lock():
                self._set_status("FAILED", error="RUNTIME_LOCK_HELD")
                return self.snapshot(lock_conflict=True)
            self.stop_event.clear()
            self.thread = threading.Thread(
                target=self._loop, name="system-paper-runtime-manager", daemon=True,
            )
            self.thread.start()
            self._set_status("RUNNING")
            self._audit("RUNTIME_START", {"process_id": self.process_id})
            return self.snapshot()

    def stop(self):
        with self._lifecycle_lock:
            if self.status == "STOPPED" and not (self.thread and self.thread.is_alive()):
                return self.snapshot(idempotent=True)
            self._set_status("STOPPING")
            self.stop_event.set()
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=10)
            self.thread = None
            self._release_db_lock()
            self._set_status("STOPPED")
            self._audit("RUNTIME_STOP", {"process_id": self.process_id})
            return self.snapshot()

    def process_once(self, dry_run: bool = False, max_entries: Optional[int] = None):
        if dry_run:
            return self.scheduler.run_once(dry_run=True, max_entries=max_entries)
        if not self.settings.runtime_manager_enabled:
            return self.snapshot(disabled=True)
        temporary_lock = False
        previous_status = self.status
        if not self._owns_db_lock:
            temporary_lock = self._acquire_db_lock()
            if not temporary_lock:
                return self.snapshot(lock_conflict=True)
        try:
            self._set_status("RUNNING")
            result = self.scheduler.run_once(dry_run=False, max_entries=max_entries)
            if result.get("status") == "BUSY":
                return result
            self.last_result = result
            self.last_run_at = datetime.now(timezone.utc)
            self.last_success_at = self.last_run_at
            self.last_error = None
            if temporary_lock and previous_status != "RUNNING":
                self._release_db_lock()
                temporary_lock = False
            self._set_status("RUNNING" if previous_status == "RUNNING" else "STOPPED", success=True)
            return result
        except Exception as exc:
            self.error_count += 1
            self.last_failure_at = datetime.now(timezone.utc)
            self.last_error = type(exc).__name__
            target = "DEGRADED" if previous_status == "RUNNING" else "FAILED"
            if temporary_lock and previous_status != "RUNNING":
                self._release_db_lock()
                temporary_lock = False
            self._set_status(target, error=self.last_error)
            self._audit("RUNTIME_ERROR", {"error": self.last_error})
            raise
        finally:
            if temporary_lock and previous_status != "RUNNING":
                self._release_db_lock()

    def dry_run(self, max_entries: Optional[int] = None):
        return self.process_once(dry_run=True, max_entries=max_entries)

    def health(self):
        state = self.snapshot()
        state["health"] = (
            "HEALTHY" if self.status == "RUNNING"
            else "WARNING" if self.status in {"STOPPED", "DEGRADED"}
            else "ERROR"
        )
        return state

    def snapshot(self, **extra):
        return {
            "status": self.status,
            "enabled": self.settings.runtime_manager_enabled,
            "paper_trading_enabled": self.settings.paper_trading_enabled,
            "paper_trading_autostart": self.settings.paper_trading_autostart,
            "scheduler_enabled": self.settings.paper_scheduler_enabled,
            "review_runtime_enabled": self.settings.review_runtime_enabled,
            "strategy_scoreboard_enabled": self.settings.strategy_scoreboard_enabled,
            "thread_alive": bool(self.thread and self.thread.is_alive()),
            "process_id": self.process_id,
            "lock_owned": self._owns_db_lock,
            "current_task": self.scheduler.current_task,
            "last_run_at": self.last_run_at,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "error_count": self.error_count,
            **extra,
        }

    def _loop(self):
        while not self.stop_event.wait(self.settings.paper_trading_poll_seconds):
            if not self.settings.paper_scheduler_enabled:
                continue
            try:
                self._renew_db_lock()
                self.process_once()
            except Exception:
                # process_once persists a sanitized failure and the loop remains recoverable.
                continue

    def _set_status(self, status, error=None, success=False):
        if status not in self.VALID_STATES:
            raise ValueError("Unknown runtime state: %s" % status)
        self.status = status
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update(
                "paper_runtime_manager", status,
                metadata={
                    "process_id": self.process_id,
                    "lock_owned": self._owns_db_lock,
                    "current_task": self.scheduler.current_task,
                    "last_result": self.last_result,
                    "error_count": self.error_count,
                },
                error=error, success=success,
            )
        finally:
            db.close()

    def _acquire_db_lock(self):
        db = self.session_factory()
        try:
            now = datetime.now(timezone.utc)
            row = db.scalar(select(SystemPaperRuntimeLock).where(
                SystemPaperRuntimeLock.lock_key == "system-paper-runtime",
            ))
            if row is not None:
                expires = self._aware(row.expires_at)
                if row.owner_id != self.owner_id and expires > now:
                    return False
                row.owner_id = self.owner_id
                row.process_id = self.process_id
                row.acquired_at = now
                row.expires_at = now + self._lock_ttl()
            else:
                db.add(SystemPaperRuntimeLock(
                    lock_key="system-paper-runtime", owner_id=self.owner_id,
                    process_id=self.process_id, acquired_at=now,
                    expires_at=now + self._lock_ttl(),
                ))
            db.commit()
            self._owns_db_lock = True
            return True
        except IntegrityError:
            db.rollback()
            return False
        finally:
            db.close()

    def _renew_db_lock(self):
        if not self._owns_db_lock:
            return False
        db = self.session_factory()
        try:
            row = db.scalar(select(SystemPaperRuntimeLock).where(
                SystemPaperRuntimeLock.lock_key == "system-paper-runtime",
                SystemPaperRuntimeLock.owner_id == self.owner_id,
            ))
            if row is None:
                self._owns_db_lock = False
                return False
            row.expires_at = datetime.now(timezone.utc) + self._lock_ttl()
            db.commit()
            return True
        finally:
            db.close()

    def _release_db_lock(self):
        if not self._owns_db_lock:
            return
        db = self.session_factory()
        try:
            row = db.scalar(select(SystemPaperRuntimeLock).where(
                SystemPaperRuntimeLock.lock_key == "system-paper-runtime",
                SystemPaperRuntimeLock.owner_id == self.owner_id,
            ))
            if row is not None:
                db.delete(row)
                db.commit()
            self._owns_db_lock = False
        finally:
            db.close()

    def _audit(self, event_type, details):
        db = self.session_factory()
        try:
            PaperAudit(db).record(event_type, details=details)
            db.commit()
        finally:
            db.close()

    def _lock_ttl(self):
        return timedelta(seconds=max(30, self.settings.paper_trading_poll_seconds * 3))

    @staticmethod
    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


_manager = None


def get_runtime_manager(settings=None):
    global _manager
    if _manager is None:
        _manager = RuntimeManager(settings)
    return _manager


def replace_runtime_manager(manager):
    global _manager
    _manager = manager
