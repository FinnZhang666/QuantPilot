from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.models import (
    SystemEquitySnapshot, SystemPaperAccount, SystemPaperOrder, SystemPaperPosition,
)
from app.database.session import get_db
from app.paper_runtime.manager import get_runtime_manager
from app.paper_runtime.service import PaperTradingService


router = APIRouter(prefix="/api/system-paper", tags=["System Paper Trading"])


def text(value):
    rendered = format(Decimal(str(value if value is not None else 0)), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


@router.get("/account", dependencies=[Depends(require_read)])
def account(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    row = db.scalar(select(SystemPaperAccount).where(
        SystemPaperAccount.account_key == "system-paper",
    ))
    if row is None:
        initial = str(settings.paper_trading_initial_cash)
        return {
            "account_key": "system-paper", "base_currency": "USD",
            "initial_cash": initial, "available_cash": initial, "reserved_cash": "0",
            "position_market_value": "0", "total_equity": initial,
            "realized_pnl": "0", "unrealized_pnl": "0", "daily_pnl": "0",
            "total_return": "0", "last_valuation_at": None,
            "status": "NOT_INITIALIZED", "paper_only": True,
        }
    return {
        "account_key": row.account_key, "base_currency": row.base_currency,
        "initial_cash": text(row.initial_cash), "available_cash": text(row.available_cash),
        "reserved_cash": text(row.reserved_cash),
        "position_market_value": text(row.position_market_value),
        "total_equity": text(row.total_equity), "realized_pnl": text(row.realized_pnl),
        "unrealized_pnl": text(row.unrealized_pnl), "daily_pnl": text(row.daily_pnl),
        "total_return": text(row.total_return), "last_valuation_at": row.last_valuation_at,
        "status": row.status, "paper_only": True,
    }


@router.get("/positions", dependencies=[Depends(require_read)])
def positions(status: str = None, db: Session = Depends(get_db)):
    query = select(SystemPaperPosition)
    if status:
        query = query.where(SystemPaperPosition.status == status.upper())
    rows = list(db.scalars(query.order_by(desc(SystemPaperPosition.open_time))))
    return {"items": [{
        "id": row.id, "symbol": row.symbol, "direction": row.direction,
        "strategy": row.strategy_name, "strategy_version": row.strategy_version,
        "quantity": text(row.quantity), "average_entry": text(row.average_entry),
        "current_price": text(row.current_price), "market_value": text(row.market_value),
        "unrealized_pnl": text(row.unrealized_pnl), "realized_pnl": text(row.realized_pnl),
        "mfe": text(row.mfe), "mae": text(row.mae), "stop": text(row.stop_price),
        "targets": row.targets_json or [], "status": row.status,
        "open_time": row.open_time, "close_time": row.close_time,
        "exit_price": text(row.exit_price), "exit_reason": row.exit_reason,
    } for row in rows], "total": len(rows)}


@router.get("/orders", dependencies=[Depends(require_read)])
def orders(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(SystemPaperOrder).order_by(desc(SystemPaperOrder.created_at))))
    return {"items": [{
        "id": row.id, "trade_plan_id": row.trade_plan_id, "symbol": row.symbol,
        "direction": row.direction, "side": row.order_side, "type": row.order_type,
        "requested_price": text(row.requested_price), "quantity": text(row.quantity),
        "status": row.status, "fill_model_version": row.fill_model_version,
        "created_at": row.created_at, "filled_at": row.filled_at,
    } for row in rows], "total": len(rows)}


@router.get("/equity", dependencies=[Depends(require_read)])
def equity(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(SystemEquitySnapshot).order_by(
        SystemEquitySnapshot.timestamp,
    )))
    return {"items": [{
        "timestamp": row.timestamp, "cash": text(row.cash),
        "position_value": text(row.position_value), "equity": text(row.equity),
        "daily_pnl": text(row.daily_pnl), "total_return": text(row.total_return),
        "drawdown": text(row.drawdown),
    } for row in rows], "total": len(rows)}


@router.get("/scoreboard", dependencies=[Depends(require_read)])
def scoreboard(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(SystemPaperPosition).where(
        SystemPaperPosition.status == "CLOSED",
    ).order_by(SystemPaperPosition.strategy_name)))
    groups = {}
    for row in rows:
        item = groups.setdefault(row.strategy_name, {
            "strategy": row.strategy_name, "trades": 0, "wins": 0, "losses": 0,
            "total_pnl": Decimal("0"), "gross_profit": Decimal("0"),
            "gross_loss": Decimal("0"), "holding_minutes": 0,
            "mfe": Decimal("0"), "mae": Decimal("0"),
        })
        pnl = Decimal(str(row.realized_pnl))
        item["trades"] += 1
        item["wins" if pnl > 0 else "losses"] += 1
        item["total_pnl"] += pnl
        if pnl > 0:
            item["gross_profit"] += pnl
        elif pnl < 0:
            item["gross_loss"] += abs(pnl)
        if row.close_time and row.open_time:
            item["holding_minutes"] += max(0, int((row.close_time - row.open_time).total_seconds() / 60))
        item["mfe"] += Decimal(str(row.mfe))
        item["mae"] += Decimal(str(row.mae))
    items = []
    for item in groups.values():
        count = item["trades"]
        profit_factor = (
            item["gross_profit"] / item["gross_loss"] if item["gross_loss"] else None
        )
        items.append({
            "strategy": item["strategy"], "trades": count,
            "wins": item["wins"], "losses": item["losses"],
            "total_pnl": text(item["total_pnl"]),
            "win_rate": item["wins"] / count if count else 0,
            "average_profit": text(item["gross_profit"] / item["wins"] if item["wins"] else 0),
            "average_loss": text(item["gross_loss"] / item["losses"] if item["losses"] else 0),
            "profit_factor": text(profit_factor) if profit_factor is not None else None,
            "average_holding_minutes": item["holding_minutes"] / count if count else 0,
            "average_mfe": text(item["mfe"] / count if count else 0),
            "average_mae": text(item["mae"] / count if count else 0),
        })
    return {"items": items, "total": len(items), "source": "SYSTEM_PAPER_ONLY"}


@router.get("/runtime", dependencies=[Depends(require_read)])
def runtime_status():
    return get_runtime_manager().snapshot()


@router.post("/runtime/start", dependencies=[Depends(require_admin)])
def runtime_start():
    return get_runtime_manager().start()


@router.post("/runtime/stop", dependencies=[Depends(require_admin)])
def runtime_stop():
    return get_runtime_manager().stop()


@router.post("/runtime/process-once", dependencies=[Depends(require_admin)])
def runtime_process_once():
    return get_runtime_manager().process_once()
