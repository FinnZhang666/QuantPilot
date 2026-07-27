from app.core.config import Settings
from app.data.providers.moomoo import MoomooConnectionManager
from app.historical.moomoo_provider import MoomooHistoricalDataProvider


def build_history_provider(settings: Settings) -> MoomooHistoricalDataProvider:
    manager = MoomooConnectionManager(
        settings.moomoo_opend_host,
        settings.moomoo_opend_port,
        settings.moomoo_connection_timeout_seconds,
    )
    return MoomooHistoricalDataProvider(
        manager,
        max_retries=settings.moomoo_history_max_retries,
        retry_delay_seconds=settings.moomoo_history_retry_delay_seconds,
        request_interval_seconds=settings.moomoo_history_request_interval_seconds,
        max_pages=settings.moomoo_history_max_pages,
    )
