from fastapi import APIRouter, Depends, HTTPException

from app.dashboard.auth import require_read
from app.database.session import get_db
from app.market_snapshot.service import SnapshotNotFound
from app.portfolio_center.errors import ValidationError
from app.symbol_overview.service import SymbolOverviewService
from app.telegram_product.formatter import TelegramFormatter
from sqlalchemy import desc, select
from app.database.models import SystemPaperAccount, SystemPaperPosition


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
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, str(exc))


@router.get("/system-paper/account")
def system_paper_preview(language: str = "zh-CN", db=Depends(get_db)):
    account = db.scalar(select(SystemPaperAccount).where(
        SystemPaperAccount.account_key == "system-paper",
    ))
    positions = list(db.scalars(select(SystemPaperPosition).where(
        SystemPaperPosition.status == "OPEN",
    ).order_by(desc(SystemPaperPosition.open_time))))
    zh = language == "zh-CN"
    if account is None:
        text = "📊 系统模拟盘\n\n尚未初始化，Runtime 当前保持关闭。" if zh else (
            "📊 System Paper Trading\n\nNot initialized; runtime remains disabled."
        )
    else:
        title = "📊 系统模拟盘" if zh else "📊 System Paper Trading"
        equity = "总权益" if zh else "Total Equity"
        cash = "可用现金" if zh else "Available Cash"
        holding = "当前持仓" if zh else "Open Positions"
        text = "%s\n\n%s: %s USD\n%s: %s USD\n%s: %s" % (
            title, equity, account.total_equity, cash, account.available_cash,
            holding, len(positions),
        )
    return {
        "parse_mode": "HTML", "text": text,
        "source": "SYSTEM_PAPER_API", "preview_equals_real": True,
    }
