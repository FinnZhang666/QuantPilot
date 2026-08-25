"""Thread-safe request coalescing and heterogeneous freshness policies."""
import threading
import heapq
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.core.errors import ControlledServiceError, ErrorCode, AppError, map_exception
from app.data_manager.models import DataEnvelope, DataFreshness


class DataRequestManager:
    def __init__(self, config_path="config/data_request_policy_v1.yaml", clock=None):
        self.config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache = {}
        self._inflight = {}
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._waiting = []
        self._active = 0
        self._sequence = 0

    def request(self, symbol, data_type, loader, *, source="LOCAL_SERVICE",
                market_timestamp=None, completeness=1.0, force=False,
                request_type="manual_analysis"):
        symbol = str(symbol or "MARKET").upper()
        key = (symbol, data_type)
        ttl = self.ttl(data_type)
        now = self.clock()
        with self._lock:
            cached = self._cache.get(key)
            if not force and cached and self._age(cached.received_timestamp, now) < ttl:
                return self._refresh_age(cached, now, ttl)
            event = self._inflight.get(key)
            owner = event is None
            if owner:
                event = threading.Event()
                self._inflight[key] = event
        if not owner:
            if not event.wait(self.config["wait_timeout_seconds"]):
                raise ControlledServiceError(AppError(
                    ErrorCode.OPEND_TIMEOUT, "data_manager", "Coalesced request timed out",
                    symbol=symbol, retryable=True, severity="warning"))
            with self._lock:
                cached = self._cache.get(key)
            if cached is None:
                raise ControlledServiceError(AppError(
                    ErrorCode.DATA_UNAVAILABLE, "data_manager", "Shared request failed",
                    symbol=symbol, retryable=True, severity="warning"))
            return self._refresh_age(cached, self.clock(), ttl)
        acquired = False
        try:
            self._acquire(request_type)
            acquired = True
            value = loader()
            received = self.clock()
            timestamp = market_timestamp or getattr(value, "timestamp", None) or received
            timestamp = self._aware(timestamp)
            age = self._age(timestamp, received)
            envelope = DataEnvelope(value, source, timestamp, received, age,
                self._freshness(age, ttl), max(0, min(1, float(completeness))))
            with self._lock:
                self._cache[key] = envelope
            return envelope
        except ControlledServiceError:
            raise
        except Exception as exc:
            raise ControlledServiceError(map_exception(exc, source, symbol)) from exc
        finally:
            if acquired:
                self._release()
            with self._lock:
                self._inflight.pop(key, None)
                event.set()

    def invalidate(self, symbol=None, data_type=None):
        with self._lock:
            keys = [key for key in self._cache if
                    (symbol is None or key[0] == symbol.upper()) and
                    (data_type is None or key[1] == data_type)]
            for key in keys:
                self._cache.pop(key, None)
            return len(keys)

    def ttl(self, data_type):
        policies = self.config["ttl_seconds"]
        if data_type not in policies:
            raise ValueError("Unknown data freshness policy: %s" % data_type)
        return int(policies[data_type])

    def priority(self, request_type):
        return int(self.config["priorities"][request_type])

    def _acquire(self, request_type):
        priority = self.priority(request_type)
        with self._condition:
            self._sequence += 1
            token = (priority, self._sequence)
            heapq.heappush(self._waiting, token)
            while self._waiting[0] != token or self._active >= int(
                    self.config["max_concurrent_requests"]):
                self._condition.wait()
            heapq.heappop(self._waiting)
            self._active += 1

    def _release(self):
        with self._condition:
            self._active = max(0, self._active - 1)
            self._condition.notify_all()

    def _refresh_age(self, envelope, now, ttl):
        age = self._age(envelope.market_timestamp or envelope.received_timestamp, now)
        return DataEnvelope(envelope.value, envelope.source, envelope.market_timestamp,
            envelope.received_timestamp, age, self._freshness(age, ttl),
            envelope.completeness, envelope.error)

    def _freshness(self, age, ttl):
        if age >= ttl:
            return DataFreshness.STALE
        if age >= ttl * float(self.config["aging_ratio"]):
            return DataFreshness.AGING
        return DataFreshness.FRESH

    @staticmethod
    def _age(then, now):
        return max(0, (DataRequestManager._aware(now) -
                       DataRequestManager._aware(then)).total_seconds())

    @staticmethod
    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
