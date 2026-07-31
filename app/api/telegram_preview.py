from fastapi import APIRouter, Depends, HTTPException

from app.dashboard.auth import require_read
from app.database.session import get_db
from app.market_snapshot.service import SnapshotNotFound
from app.symbol_overview.service import SymbolOverviewService
from app.telegram_product.formatter import TelegramFormatter


router = APIRouter(
    prefix="/api/telegram-preview", tags=["Telegram Product Preview"],
    dependencies=[Depends(require_read)],
)


@router.get("/{symbol}")
def telegram_preview(symbol: str, market: str = "US", language: str = "zh-CN", db=Depends(get_db)):
    try:
        overview = SymbolOverviewService(db).get(symbol, market)
        return TelegramFormatter().overview(overview, language)
    except SnapshotNotFound as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
