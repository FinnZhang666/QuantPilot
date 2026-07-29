from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.health import router as health_router
from app.api.moomoo import router as moomoo_router
from app.api.history import router as history_router
from app.api.realtime import router as realtime_router
from app.api.features import router as features_router
from app.api.watchlist import router as watchlist_router
from app.api.strategy import router as strategy_router
from app.api.backtest import router as backtest_router
from app.api.opportunities import router as opportunities_router
from app.api.runtime import router as runtime_router
from app.api.dashboard import router as dashboard_api_router
from app.api.development import router as development_router
from app.api.market_regime import router as market_regime_router
from app.api.candidate_pool import router as candidate_pool_router
from app.api.review import router as review_router
from app.api.ai_review import router as ai_review_router
from app.api.platform import router as platform_router
from app.dashboard.routes import router as dashboard_router
from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.init import create_schema
from app.database.session import get_engine
from app.realtime.factory import peek_realtime_manager
from app.core.enums import RealtimeServiceState
from app.runtime.realtime_runtime import get_runtime
from app.version import VERSION


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(
        settings.log_level, settings.log_directory,
        settings.log_max_bytes, settings.log_backup_count,
    )
    create_schema(get_engine())
    try:
        yield
    finally:
        runtime = get_runtime()
        if runtime.status != "STOPPED":
            runtime.stop()
        manager = peek_realtime_manager()
        if manager and manager.status != RealtimeServiceState.STOPPED:
            manager.stop()


app = FastAPI(title="QuantPilot", version=VERSION, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request, exc):
    return JSONResponse(status_code=422, content={"detail": "请求参数无效，请检查格式、范围和必填字段。"})


app.include_router(health_router)
app.include_router(api_router)
app.include_router(moomoo_router)
app.include_router(history_router)
app.include_router(realtime_router)
app.include_router(features_router)
app.include_router(watchlist_router)
app.include_router(strategy_router)
app.include_router(backtest_router)
app.include_router(opportunities_router)
app.include_router(runtime_router)
app.include_router(dashboard_api_router)
app.include_router(development_router)
app.include_router(market_regime_router)
app.include_router(candidate_pool_router)
app.include_router(review_router)
app.include_router(ai_review_router)
app.include_router(platform_router)
app.include_router(dashboard_router)
app.mount(
    "/dashboard/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "dashboard" / "static")),
    name="dashboard-static",
)
