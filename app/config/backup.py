from app.config.settings import settings


def backup_config():
    return {
        "directory": settings.backup_directory,
        "daily_retention": settings.backup_daily_retention,
        "weekly_retention": settings.backup_weekly_retention,
    }
