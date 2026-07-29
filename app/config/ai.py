from app.config.settings import settings


def ai_config():
    return {
        "enabled": settings.ai_review_enabled,
        "provider": settings.ai_review_provider,
        "model": settings.ai_review_model,
    }
