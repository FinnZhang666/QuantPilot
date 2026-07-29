import platform
import shutil
from pathlib import Path
from typing import Dict, List

from sqlalchemy import text

from app.config.settings import Settings


def _item(name: str, status: str, message: str) -> Dict[str, str]:
    return {"name": name, "status": status, "message": message}


def validate_environment(settings: Settings, db=None) -> Dict[str, object]:
    checks: List[Dict[str, str]] = []
    version = tuple(int(value) for value in platform.python_version_tuple())
    checks.append(_item(
        "python", "PASS" if (3, 9) <= version < (3, 10) else "FAILED",
        "Python %s（要求 >=3.9,<3.10）" % platform.python_version(),
    ))
    try:
        if db is None:
            raise RuntimeError("未提供数据库会话")
        db.execute(text("SELECT 1"))
        checks.append(_item("database", "PASS", "数据库连接正常"))
    except Exception as exc:
        checks.append(_item("database", "FAILED", "数据库不可用：%s" % type(exc).__name__))
    checks.append(_item(
        "telegram",
        "PASS" if settings.telegram_enabled and settings.telegram_bot_token
        and settings.telegram_chat_id_list() else "WARNING",
        "Telegram已配置" if settings.telegram_enabled else "Telegram模块未启用",
    ))
    checks.append(_item(
        "dashboard", "PASS" if settings.dashboard_admin_token else "WARNING",
        "管理员Token已配置" if settings.dashboard_admin_token else "管理员Token未配置",
    ))
    ai_ready = (
        not settings.ai_review_enabled or settings.ai_review_provider == "mock" or
        bool(settings.ai_review_base_url and settings.ai_review_model)
    )
    checks.append(_item(
        "ai_provider", "PASS" if ai_ready else "FAILED",
        "AI Provider配置有效" if ai_ready else "AI Provider缺少地址或模型",
    ))
    checks.append(_item(
        "runtime", "PASS" if settings.realtime_timeframe_list() else "FAILED",
        "Runtime周期配置有效",
    ))
    free_gb = shutil.disk_usage(Path(settings.database_url.removeprefix("sqlite:///")).parent).free / 1024 ** 3
    disk_status = "FAILED" if free_gb < settings.moomoo_min_free_disk_gb else (
        "WARNING" if free_gb < settings.moomoo_warn_free_disk_gb else "PASS"
    )
    checks.append(_item("disk", disk_status, "磁盘剩余 %.2f GB" % free_gb))
    overall = "FAILED" if any(row["status"] == "FAILED" for row in checks) else (
        "WARNING" if any(row["status"] == "WARNING" for row in checks) else "PASS"
    )
    return {"status": overall, "checks": checks}
