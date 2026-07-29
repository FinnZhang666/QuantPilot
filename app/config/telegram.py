from app.config.settings import settings


def telegram_config():
    return {
        "enabled": settings.telegram_enabled,
        "chat_count": len(settings.telegram_chat_id_list()),
        "admin_count": len(settings.telegram_admin_id_set()),
    }
