from app.config.settings import settings


def logging_config():
    return {
        "level": settings.log_level,
        "directory": settings.log_directory,
        "max_bytes": settings.log_max_bytes,
        "backup_count": settings.log_backup_count,
        "json_enabled": settings.log_json_enabled,
    }
