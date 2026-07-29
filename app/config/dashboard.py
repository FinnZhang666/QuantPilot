from app.config.settings import settings


def dashboard_config():
    return {
        "readonly_public": settings.dashboard_readonly_public,
        "admin_token_configured": bool(settings.dashboard_admin_token),
    }
