from app.config.settings import settings


def database_config():
    return {"url": settings.database_url}
