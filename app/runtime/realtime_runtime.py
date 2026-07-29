import asyncio
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import desc, select

from app.core.config import Settings, get_settings
from app.core.enums import RealtimeServiceState
from app.database.models import RealtimeBar, WatchlistItem, WatchlistTimeframe
from app.database.session import get_session_factory
from app.notifications.telegram import TelegramNotificationProvider
from app.notifications.telegram_commands import TelegramCommandPoller
from app.realtime.factory import get_realtime_manager
from app.runtime.opportunity_pipeline import OpportunityPipeline
from app.runtime.runtime_state import RuntimeStateRepository


class RealtimeOpportunityRuntime:
    def __init__(
        self, settings: Optional[Settings] = None, session_factory=None,
        realtime_manager=None, pipeline_factory=None,
    ):
        self.settings = settings or get_settings()
        self.session_factory = session_factory or get_session_factory()
        self.realtime_manager = realtime_manager or get_realtime_manager(self.settings)
        self.pipeline_factory = pipeline_factory
        self.stop_event = threading.Event()
        self.thread = None
        self.lock = threading.RLock()
        self.status = "STOPPED"
        self.last_processed: Dict[str, datetime] = {}
        self.last_strategy_run_at = None
        self.processed_count = 0
        self.error_count = 0
        self._last_opend_connected = None
        self.telegram_poller = TelegramCommandPoller(self.settings, self.session_factory)

    def start(self) -> Dict[str, object]:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return self.snapshot(idempotent=True)
            self.stop_event.clear()
            self.status = "STARTING"
            self._save_state()
            try:
                if self.realtime_manager.status == RealtimeServiceState.STOPPED:
                    self.realtime_manager.start()
            except Exception as exc:
                self.status = "DEGRADED"
                self._save_state(error="OpenD连接失败：" + str(exc))
            self.thread = threading.Thread(
                target=self._loop, name="moomoo-opportunity-runtime", daemon=False,
            )
            self.thread.start()
            self.telegram_poller.start()
            self.status = "RUNNING" if self.realtime_manager.status == RealtimeServiceState.CONNECTED else "DEGRADED"
            self._notify_event("Runtime已启动", "实时机会Runtime已启动，当前状态：" + self.status)
            self._save_state(success=True)
            return self.snapshot()

    def stop(self) -> Dict[str, object]:
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                self.status = "STOPPED"
                self._save_state()
                self._save_pipeline_stopped()
                return self.snapshot(idempotent=True)
            self.stop_event.set()
        self.thread.join(timeout=max(5.0, self.settings.runtime_poll_interval_seconds * 3))
        self.telegram_poller.stop()
        self.status = "STOPPED"
        self._save_state()
        self._save_pipeline_stopped()
        return self.snapshot()

    def process_once(self) -> Dict[str, object]:
        results = []
        db = self.session_factory()
        try:
            configured = set(self.settings.realtime_timeframe_list())
            pairs = db.execute(select(WatchlistItem.symbol, WatchlistTimeframe.timeframe).join(
                WatchlistTimeframe, WatchlistTimeframe.watchlist_item_id == WatchlistItem.id,
            ).where(
                WatchlistItem.enabled.is_(True), WatchlistTimeframe.enabled.is_(True),
                WatchlistTimeframe.timeframe.in_(configured),
            )).all()
            pipeline = self.pipeline_factory(db) if self.pipeline_factory else OpportunityPipeline(db, self.settings)
            for symbol, timeframe in pairs:
                full_symbol = "US." + symbol
                latest = db.scalar(select(RealtimeBar).where(
                    RealtimeBar.symbol == full_symbol, RealtimeBar.interval == timeframe,
                    RealtimeBar.is_closed.is_(True),
                ).order_by(desc(RealtimeBar.timestamp_utc)).limit(1))
                if latest is None:
                    continue
                key = symbol + "/" + timeframe
                timestamp = self._aware(latest.timestamp_utc)
                if self.last_processed.get(key) == timestamp:
                    continue
                outcome = pipeline.process_closed_bar(symbol, timeframe)
                results.append(outcome)
                if outcome.get("status") != "ERROR":
                    self.last_processed[key] = timestamp
                    self.processed_count += 1
                    self.last_strategy_run_at = datetime.now(timezone.utc)
                else:
                    self.error_count += 1
            self._check_connection_transition()
            self._save_state(success=bool(results and not any(r.get("status") == "ERROR" for r in results)))
        finally:
            db.close()
        return {"processed": len(results), "results": results}

    def snapshot(self, idempotent: bool = False) -> Dict[str, object]:
        health = self.realtime_manager.get_status()
        return {
            "status": self.status, "status_text": {
                "STOPPED": "已停止", "STARTING": "正在启动",
                "RUNNING": "运行中", "DEGRADED": "服务降级", "FAILED": "严重异常",
            }.get(self.status, self.status),
            "opend_connected": health.opend_connected,
            "last_market_message_at": health.last_message_at,
            "last_strategy_run_at": self.last_strategy_run_at,
            "processed_count": self.processed_count, "error_count": self.error_count,
            "thread_alive": bool(self.thread and self.thread.is_alive()),
            "idempotent": idempotent,
        }

    def _loop(self):
        while not self.stop_event.wait(self.settings.runtime_poll_interval_seconds):
            try:
                self.process_once()
            except Exception as exc:
                self.error_count += 1
                self.status = "DEGRADED"
                self._save_state(error=type(exc).__name__ + "：" + str(exc))

    def _check_connection_transition(self):
        connected = self.realtime_manager.get_status().opend_connected
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update(
                "opend", "CONNECTED" if connected else "DISCONNECTED",
                success=connected,
            )
        finally:
            db.close()
        if self._last_opend_connected is None:
            self._last_opend_connected = connected
            return
        if connected != self._last_opend_connected:
            if connected:
                self._notify_event("OpenD已恢复", "OpenD连接已恢复，Runtime继续处理闭合K线。")
                self.status = "RUNNING"
            else:
                self._notify_event("OpenD已断开", "OpenD连接已断开，Runtime进入降级状态并等待现有重连机制恢复。")
                self.status = "DEGRADED"
            self._last_opend_connected = connected

    def _notify_event(self, subject: str, text: str):
        status = "DEGRADED"
        error = None
        try:
            result = asyncio.run(TelegramNotificationProvider(self.settings).send_text("【%s】\n%s" % (subject, text)))
            status = "CONNECTED" if result.status == "sent" else (
                "DISABLED" if result.status == "disabled" else "DEGRADED"
            )
            error = result.error
        except Exception as exc:
            self.error_count += 1
            error = type(exc).__name__
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update(
                "telegram", status, error=error, success=status == "CONNECTED",
            )
        finally:
            db.close()

    def _save_state(self, error: Optional[str] = None, success: bool = False):
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update(
                "realtime_runtime", self.status,
                metadata={
                    "processed_count": self.processed_count, "error_count": self.error_count,
                    "last_strategy_run_at": self.last_strategy_run_at.isoformat() if self.last_strategy_run_at else None,
                    "last_processed": {key: value.isoformat() for key, value in self.last_processed.items()},
                },
                error=error, success=success,
            )
        finally:
            db.close()

    def _save_pipeline_stopped(self):
        db = self.session_factory()
        try:
            RuntimeStateRepository(db).update("opportunity_pipeline", "STOPPED")
        finally:
            db.close()

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


_runtime = None


def get_runtime(settings: Optional[Settings] = None):
    global _runtime
    if _runtime is None:
        _runtime = RealtimeOpportunityRuntime(settings)
    return _runtime


def replace_runtime(runtime):
    global _runtime
    _runtime = runtime
