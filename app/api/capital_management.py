from decimal import Decimal
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.capital_management.service import CapitalManagementService
from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.models import SystemPaperAccount
from app.database.session import get_db


router = APIRouter(prefix="/api/capital-management", tags=["Capital Management"],
                   dependencies=[Depends(require_read)])
internal_router = APIRouter(prefix="/internal/capital-management", include_in_schema=False,
                            dependencies=[Depends(require_admin)])


def _account(db):
    row = db.scalar(select(SystemPaperAccount).where(
        SystemPaperAccount.account_key == "system-paper"))
    return row


@router.get("/summary", include_in_schema=False)
def summary(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    account = _account(db)
    if account is None:
        initial = Decimal(str(settings.paper_trading_initial_cash))
        account = SimpleNamespace(initial_cash=initial, total_equity=initial,
            available_cash=initial, realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"))
        return CapitalManagementService(db, settings)._empty_summary(account, initial)
    return CapitalManagementService(db, settings).summary(account, create=False)


@router.get("/transfers", include_in_schema=False)
def transfers(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    account = _account(db)
    if account is None:
        return {"items": [], "limit": limit, "offset": offset}
    rows = CapitalManagementService(db, settings).transfers(account.id, limit, offset)
    return {"items": [{"transfer_id": row.transfer_id, "timestamp": row.timestamp,
        "source_bucket": row.source_bucket, "destination_bucket": row.destination_bucket,
        "amount": str(row.amount), "reason": row.reason, "trigger_profit": str(row.trigger_profit),
        "strategy_source": row.strategy_source, "strategy_version": row.strategy_version,
        "allocation_rule_version": row.allocation_rule_version, "status": row.status}
        for row in rows], "limit": limit, "offset": offset}


@internal_router.post("/process")
def process(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    account = _account(db)
    if account is None:
        from app.paper_runtime.service import PaperTradingService
        account = PaperTradingService(db, settings).account()
    try:
        result = CapitalManagementService(db, settings).process(account)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise HTTPException(409, "Profit Lock allocation failed safely.") from exc
