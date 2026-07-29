from app.config.settings import settings


def runtime_config():
    return {
        "enabled": settings.realtime_runtime_enabled,
        "timeframes": settings.realtime_timeframe_list(),
        "poll_interval_seconds": settings.runtime_poll_interval_seconds,
    }
