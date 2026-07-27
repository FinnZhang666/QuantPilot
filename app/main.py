from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.init import create_schema
from app.database.session import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    create_schema(get_engine())
    yield


app = FastAPI(title="Moomoo Quant", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(api_router)
