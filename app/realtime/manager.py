import queue
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

from app.core.enums import MarketSession, RealtimeDataType, RealtimeServiceState
from app.database.session import get_session_factory
from app.historical.timezone import NEW_YORK
from app.realtime.models import (
    RealtimeBarData,
    RealtimeHealthReport,
    RealtimeQuoteData,
    RealtimeTickerData,
    SubscriptionResult,
)
from app.realtime.repository import RealtimeRepository
from app.realtime.session import MarketSessionStateMachine

STATUS_TEXT = {
    "STOPPED": "已停止", "STARTING": "正在启动", "CONNECTED": "已连接",
    "DEGRADED": "服务降级", "RECONNECTING": "正在重连", "FAILED": "启动失败",
}


class RealtimeSubscriptionManager:
    def __init__(
        self,
        provider_factory: Callable[[Callable[[Any], None]], Any],
        symbols: Iterable[str],
        data_types: Iterable[RealtimeDataType],
        queue_capacity: int = 10000,
        batch_size: int = 200,
        flush_interval: float = 1.0,
        max_reconnect_attempts: int = 5,
        reconnect_delay: float = 5.0,
        stale_regular: int = 30,
        stale_extended: int = 120,
        health_interval: float = 10.0,
        session_factory: Optional[Callable[[], Any]] = None,
    ):
        self.provider_factory = provider_factory
        self.requested_symbols = list(dict.fromkeys(value.upper() for value in symbols))
        self.requested_types = set(data_types)
        self.queue = queue.Queue(maxsize=queue_capacity)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.stale_regular = stale_regular
        self.stale_extended = stale_extended
        self.health_interval = health_interval
        self.session_factory = session_factory or get_session_factory()
        self.provider = None
        self.writer_thread = None
        self.health_thread = None
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.status = RealtimeServiceState.STOPPED
        self.subscriptions: Dict[str, Set[RealtimeDataType]] = {}
        self.latest_quotes: Dict[str, RealtimeQuoteData] = {}
        self.latest_tickers: Dict[str, RealtimeTickerData] = {}
        self.latest_bars: Dict[str, RealtimeBarData] = {}
        self.received_count = self.persisted_count = self.duplicate_count = 0
        self.received_by_type: Dict[str, int] = {"QUOTE": 0, "TICKER": 0, "KLINE_1M": 0}
        self.dropped_count = self.error_count = self.reconnect_count = 0
        self.error_samples: List[str] = []
        self.max_queue_size = 0
        self.seen_identities: OrderedDict = OrderedDict()
        self.seen_identity_limit = max(queue_capacity * 10, 10000)
        self.last_message_at = self.last_quote_at = self.last_ticker_at = self.last_bar_at = None
        self.started_at = None
        self.session_engine = MarketSessionStateMachine()

    def start(self) -> SubscriptionResult:
        with self.lock:
            if self.status in {RealtimeServiceState.STARTING, RealtimeServiceState.CONNECTED}:
                return self._current_result(skipped=True)
            self.status = RealtimeServiceState.STARTING
            self.stop_event.clear()
            db = self.session_factory()
            try:
                valid, invalid = RealtimeRepository(db).valid_symbols(self.requested_symbols)
            finally:
                db.close()
            try:
                self.provider = self.provider_factory(self.enqueue)
                if hasattr(self.provider, "on_error"):
                    self.provider.on_error = self.record_callback_error
                self.provider.connect()
                self._ensure_writer()
                self._ensure_health_monitor()
                result = self.subscribe_symbols(valid, self.requested_types)
            except Exception as exc:
                if self.provider:
                    self.provider.close()
                self.provider = None
                self.status = RealtimeServiceState.FAILED
                self.error_count += 1
                self._save_status(error_code="START_FAILED", error_message=str(exc))
                raise
            for symbol, message in invalid.items():
                result.failed[symbol] = {"ALL": message}
            self.started_at = datetime.now(timezone.utc)
            self.status = RealtimeServiceState.CONNECTED if result.successful else RealtimeServiceState.DEGRADED
            self._save_status()
            return result

    def stop(self) -> SubscriptionResult:
        with self.lock:
            result = self.unsubscribe_symbols(list(self.subscriptions), self.requested_types)
            if self.provider:
                self.provider.close()
            self.stop_event.set()
        if self.writer_thread and self.writer_thread.is_alive():
            self.writer_thread.join(timeout=max(60.0, self.flush_interval * 3))
            if self.writer_thread.is_alive():
                self.error_count += 1
                self.error_samples.append("停止服务时队列未能在60秒内安全排空")
        if self.health_thread and self.health_thread.is_alive():
            self.health_thread.join(timeout=max(2.0, self.health_interval + 1))
        with self.lock:
            self.provider = None
            self.status = RealtimeServiceState.STOPPED
            self._save_status(stopped_at=datetime.now(timezone.utc))
        return result

    def subscribe_symbols(self, symbols: Iterable[str], data_types: Iterable[RealtimeDataType]) -> SubscriptionResult:
        result = SubscriptionResult()
        requested = list(dict.fromkeys(value.upper() for value in symbols))
        db = self.session_factory()
        try:
            valid, invalid = RealtimeRepository(db).valid_symbols(requested)
        finally:
            db.close()
        for symbol, message in invalid.items():
            result.failed[symbol] = {"ALL": message}
        for symbol in valid:
            missing = set(data_types) - self.subscriptions.get(symbol, set())
            if not missing:
                result.skipped[symbol] = sorted(item.value for item in data_types)
                continue
            failures = self.provider.subscribe([symbol], missing)
            failed_types = {key.split(":", 1)[1]: value for key, value in failures.items()}
            successful = [item for item in missing if item.value not in failed_types]
            if successful:
                self.subscriptions.setdefault(symbol, set()).update(successful)
                result.successful[symbol] = sorted(item.value for item in successful)
            if failed_types:
                result.failed[symbol] = failed_types
        return result

    def unsubscribe_symbols(self, symbols: Iterable[str], data_types: Iterable[RealtimeDataType]) -> SubscriptionResult:
        result = SubscriptionResult()
        for symbol in list(dict.fromkeys(value.upper() for value in symbols)):
            existing = self.subscriptions.get(symbol, set()) & set(data_types)
            if not existing:
                result.skipped[symbol] = sorted(item.value for item in data_types)
                continue
            failures = self.provider.unsubscribe([symbol], existing) if self.provider else {}
            failed_types = {key.split(":", 1)[1]: value for key, value in failures.items()}
            removed = [item for item in existing if item.value not in failed_types]
            self.subscriptions[symbol].difference_update(removed)
            if not self.subscriptions[symbol]:
                del self.subscriptions[symbol]
            result.successful[symbol] = sorted(item.value for item in removed)
            if failed_types:
                result.failed[symbol] = failed_types
        return result

    def resubscribe_all(self) -> SubscriptionResult:
        wanted = {symbol: set(types) for symbol, types in self.subscriptions.items()}
        self.subscriptions.clear()
        combined = SubscriptionResult()
        for symbol, types in wanted.items():
            result = self.subscribe_symbols([symbol], types)
            combined.successful.update(result.successful)
            combined.failed.update(result.failed)
        return combined

    def enqueue(self, item: Any) -> None:
        now = datetime.now(timezone.utc)
        with self.lock:
            self.received_count += 1
            identity = self._identity(item)
            if identity in self.seen_identities:
                self.duplicate_count += 1
                self.seen_identities.move_to_end(identity)
            else:
                self.seen_identities[identity] = None
                if len(self.seen_identities) > self.seen_identity_limit:
                    self.seen_identities.popitem(last=False)
            self.last_message_at = now
            if isinstance(item, RealtimeQuoteData):
                self.received_by_type["QUOTE"] += 1
                self.latest_quotes[item.symbol] = item
                self.last_quote_at = now
            elif isinstance(item, RealtimeTickerData):
                self.received_by_type["TICKER"] += 1
                self.latest_tickers[item.symbol] = item
                self.last_ticker_at = now
            elif isinstance(item, RealtimeBarData):
                self.received_by_type["KLINE_1M"] += 1
                self.latest_bars[item.symbol] = item
                self.last_bar_at = now
        try:
            self.queue.put_nowait(item)
            self.max_queue_size = max(self.max_queue_size, self.queue.qsize())
        except queue.Full:
            with self.lock:
                self.dropped_count += 1
                self.status = RealtimeServiceState.DEGRADED

    @staticmethod
    def _identity(item: Any) -> Any:
        if isinstance(item, RealtimeQuoteData):
            return ("QUOTE", item.symbol, item.timestamp_utc, item.data_source)
        if isinstance(item, RealtimeTickerData):
            return ("TICKER", item.symbol, item.sequence, item.ticker_time_utc, item.data_source)
        if isinstance(item, RealtimeBarData):
            return ("KLINE_1M", item.symbol, item.interval.value, item.timestamp_utc, item.data_source)
        return ("UNKNOWN", id(item))

    def record_callback_error(self, exc: Exception) -> None:
        with self.lock:
            self.error_count += 1
            sample = type(exc).__name__ + "：" + str(exc)
            if sample not in self.error_samples and len(self.error_samples) < 10:
                self.error_samples.append(sample)
            self.status = RealtimeServiceState.DEGRADED

    def _ensure_writer(self) -> None:
        if self.writer_thread and self.writer_thread.is_alive():
            return
        self.writer_thread = threading.Thread(target=self._writer_loop, name="moomoo-realtime-writer", daemon=False)
        self.writer_thread.start()

    def _ensure_health_monitor(self) -> None:
        if self.health_thread and self.health_thread.is_alive():
            return
        self.health_thread = threading.Thread(target=self._health_loop, name="moomoo-realtime-health", daemon=False)
        self.health_thread.start()

    def _health_loop(self) -> None:
        previous = self.session_engine.current_session
        while not self.stop_event.wait(self.health_interval):
            now = datetime.now(timezone.utc)
            market_state = None
            try:
                raw = self.provider.market_state(sorted(self.subscriptions)) if self.provider and self.subscriptions else None
                records = raw.to_dict("records") if hasattr(raw, "to_dict") else list(raw or [])
                if records:
                    market_state = records[0].get("market_state")
            except Exception:
                self.error_count += 1
            result = self.session_engine.update(now, market_state)
            if previous != MarketSession.UNKNOWN and previous != result.session:
                db = self.session_factory()
                try:
                    RealtimeRepository(db).record_session_event(
                        previous.value, result.session.value, result.source, result.reason,
                        now.astimezone(NEW_YORK),
                    )
                finally:
                    db.close()
            previous = result.session
            if self.check_stale(now):
                self.reconnect("实时行情超过健康阈值未收到消息")

    def _writer_loop(self) -> None:
        batch: List[Any] = []
        deadline = time.monotonic() + self.flush_interval
        while not self.stop_event.is_set() or not self.queue.empty() or batch:
            timeout = max(0.0, deadline - time.monotonic())
            try:
                batch.append(self.queue.get(timeout=min(timeout, 0.2)))
            except queue.Empty:
                pass
            if batch and (len(batch) >= self.batch_size or time.monotonic() >= deadline or (self.stop_event.is_set() and self.queue.empty())):
                db = self.session_factory()
                try:
                    persisted, duplicates = RealtimeRepository(db).persist(batch)
                    with self.lock:
                        self.persisted_count += persisted
                        self.duplicate_count += duplicates
                except Exception:
                    with self.lock:
                        self.error_count += 1
                        self.status = RealtimeServiceState.DEGRADED
                finally:
                    db.close()
                    for _ in batch:
                        self.queue.task_done()
                batch = []
                deadline = time.monotonic() + self.flush_interval

    def reconnect(self, reason: str) -> bool:
        wanted = {symbol: set(types) for symbol, types in self.subscriptions.items()}
        for attempt in range(1, self.max_reconnect_attempts + 1):
            self.status = RealtimeServiceState.RECONNECTING
            self.reconnect_count += 1
            try:
                if self.provider:
                    self.provider.close()
                self.provider = self.provider_factory(self.enqueue)
                if hasattr(self.provider, "on_error"):
                    self.provider.on_error = self.record_callback_error
                self.provider.connect()
                self.subscriptions.clear()
                for symbol, types in wanted.items():
                    self.subscribe_symbols([symbol], types)
                self.status = RealtimeServiceState.CONNECTED
                self._save_status(error_message=reason)
                return True
            except Exception:
                self.error_count += 1
                if attempt < self.max_reconnect_attempts:
                    time.sleep(self.reconnect_delay)
        self.status = RealtimeServiceState.FAILED
        self._save_status(error_code="RECONNECT_FAILED", error_message=reason)
        return False

    def check_stale(self, now: Optional[datetime] = None, liquid_symbols: Optional[Set[str]] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        result = self.session_engine.update(now)
        threshold = self.stale_regular if result.session == MarketSession.REGULAR else self.stale_extended
        if self.last_message_at is None:
            return False
        stale = (now - self.last_message_at).total_seconds() > threshold
        liquid_symbols = liquid_symbols or {"US.QQQ", "US.SPY"}
        has_liquid = any(symbol in self.subscriptions for symbol in liquid_symbols)
        if stale and has_liquid:
            self.status = RealtimeServiceState.DEGRADED
            return True
        return False

    def get_status(self) -> RealtimeHealthReport:
        now = datetime.now(timezone.utc)
        session = self.session_engine.update(now).session
        warnings = []
        if self.dropped_count:
            warnings.append("队列曾满，存在丢弃数据")
        if self.status == RealtimeServiceState.DEGRADED:
            warnings.append("实时行情服务处于降级状态")
        return RealtimeHealthReport(
            status=self.status.value,
            opend_connected=self.provider is not None and self.status in {RealtimeServiceState.CONNECTED, RealtimeServiceState.DEGRADED},
            current_session=session,
            subscribed_symbol_count=len(self.subscriptions),
            subscribed_types=set().union(*self.subscriptions.values()) if self.subscriptions else set(),
            queue_size=self.queue.qsize(), queue_capacity=self.queue.maxsize,
            received_count=self.received_count, persisted_count=self.persisted_count,
            duplicate_count=self.duplicate_count, dropped_count=self.dropped_count,
            error_count=self.error_count, reconnect_count=self.reconnect_count,
            last_message_at=self.last_message_at, warnings=warnings,
        )

    def _save_status(self, **extra: Any) -> None:
        db = self.session_factory()
        try:
            RealtimeRepository(db).save_status(
                status=self.status.value, started_at=self.started_at,
                last_connected_at=datetime.now(timezone.utc) if self.status == RealtimeServiceState.CONNECTED else None,
                reconnect_count=self.reconnect_count,
                subscribed_symbols_json=sorted(self.subscriptions),
                subscribed_types_json=sorted({item.value for values in self.subscriptions.values() for item in values}),
                last_message_at=self.last_message_at, last_quote_at=self.last_quote_at,
                last_ticker_at=self.last_ticker_at, last_bar_at=self.last_bar_at,
                metadata_json={"received": self.received_count, "received_by_type": self.received_by_type, "persisted": self.persisted_count, "duplicates": self.duplicate_count, "dropped": self.dropped_count, "errors": self.error_count, "error_samples": self.error_samples, "queue_size": self.queue.qsize()},
                **extra
            )
        finally:
            db.close()

    def _current_result(self, skipped: bool = False) -> SubscriptionResult:
        result = SubscriptionResult()
        for symbol, types in self.subscriptions.items():
            target = result.skipped if skipped else result.successful
            target[symbol] = sorted(item.value for item in types)
        return result
