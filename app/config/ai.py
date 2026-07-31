from app.config.settings import settings


def ai_config():
    return {
        "ai_review": {
            "enabled": settings.ai_review_enabled,
            "provider": settings.ai_review_provider,
            "model": settings.ai_review_model,
        },
        "ai_companion": {
            "enabled": settings.ai_companion_enabled,
            "provider": settings.ai_companion_provider,
            "model": settings.ai_companion_model,
            "default_language": settings.ai_companion_default_language,
        },
    }
