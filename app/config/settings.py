"""统一Settings入口；app.core.config保留为兼容层。"""

from app.core.config import Settings, get_settings


class _SettingsProxy:
    def __getattr__(self, name):
        return getattr(get_settings(), name)


settings = _SettingsProxy()

__all__ = ["Settings", "get_settings", "settings"]
