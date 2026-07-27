from typing import Iterable, Optional

from app.core.config import Settings, get_settings
from app.core.enums import RealtimeDataType
from app.data.providers.moomoo import MoomooConnectionManager
from app.realtime.manager import RealtimeSubscriptionManager
from app.realtime.normalizer import MoomooRealtimeNormalizer
from app.realtime.providers.moomoo import MoomooRealtimeProvider

_manager: Optional[RealtimeSubscriptionManager] = None


def build_realtime_manager(
    settings: Optional[Settings] = None,
    symbols: Optional[Iterable[str]] = None,
) -> RealtimeSubscriptionManager:
    settings = settings or get_settings()
    chosen = list(symbols) if symbols is not None else settings.realtime_symbol_list()

    def provider_factory(on_data):
        connection = MoomooConnectionManager(
            settings.moomoo_opend_host,
            settings.moomoo_opend_port,
            settings.moomoo_connection_timeout_seconds,
        )
        return MoomooRealtimeProvider(connection, on_data, MoomooRealtimeNormalizer())

    return RealtimeSubscriptionManager(
        provider_factory=provider_factory,
        symbols=chosen,
        data_types={
            RealtimeDataType.QUOTE,
            RealtimeDataType.TICKER,
            RealtimeDataType.KLINE_1M,
            RealtimeDataType.MARKET_STATE,
        },
        queue_capacity=settings.realtime_queue_max_size,
        batch_size=settings.realtime_batch_size,
        flush_interval=settings.realtime_flush_interval_seconds,
        max_reconnect_attempts=settings.realtime_reconnect_max_attempts,
        reconnect_delay=settings.realtime_reconnect_delay_seconds,
        stale_regular=settings.realtime_stale_seconds_regular,
        stale_extended=settings.realtime_stale_seconds_extended,
        health_interval=settings.realtime_health_check_interval_seconds,
    )


def get_realtime_manager(settings: Optional[Settings] = None) -> RealtimeSubscriptionManager:
    global _manager
    if _manager is None:
        _manager = build_realtime_manager(settings)
    return _manager


def replace_realtime_manager(manager: Optional[RealtimeSubscriptionManager]) -> None:
    global _manager
    _manager = manager


def peek_realtime_manager() -> Optional[RealtimeSubscriptionManager]:
    return _manager
