"""Authenticated read-only endpoints for the Windows data node."""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.dashboard.auth import require_admin
from app.database.models import CandidateSignal, MoomooConnectionCheck, RealtimeQuote, RealtimeServiceStatus, SystemPaperPosition
from app.database.session import get_db

router = APIRouter(prefix="/api", tags=["Windows Local Node"], dependencies=[Depends(require_admin)])


def _value(value):
    if isinstance(value, Decimal): return format(value, "f")
    if isinstance(value, datetime): return value.isoformat()
    return value


@router.get("/market-context")
def market_context(db: Session = Depends(get_db)):
    quote = db.scalar(select(RealtimeQuote).order_by(desc(RealtimeQuote.timestamp_utc), desc(RealtimeQuote.id)).limit(1))
    service = db.scalar(select(RealtimeServiceStatus).where(RealtimeServiceStatus.service_name == "moomoo_realtime"))
    check = db.scalar(select(MoomooConnectionCheck).order_by(desc(MoomooConnectionCheck.checked_at), desc(MoomooConnectionCheck.id)).limit(1))
    now = datetime.now(timezone.utc)
    quote_time = quote.timestamp_utc if quote else None
    if quote_time is not None and quote_time.tzinfo is None: quote_time = quote_time.replace(tzinfo=timezone.utc)
    age = None if quote_time is None else max(0, int((now - quote_time).total_seconds()))
    return {"opend": "HEALTHY" if check and check.opend_reachable and check.opend_logged_in else "OFFLINE", "realtime": service.status if service else "STOPPED", "market_session": quote.market_session if quote else "UNKNOWN", "latest_symbol": quote.symbol if quote else None, "latest_price": _value(quote.last_price) if quote else None, "latest_timestamp": _value(quote_time), "market_data_age_seconds": age, "market_data_freshness": "HEALTHY" if age is not None and age <= 900 else ("DEGRADED" if age is not None else "OFFLINE"), "real_trading": "DISABLED"}


@router.get("/position/{symbol}")
def position(symbol: str, db: Session = Depends(get_db)):
    clean = symbol.upper().replace("US.", "")
    rows = list(db.scalars(select(SystemPaperPosition).where(SystemPaperPosition.symbol == clean).order_by(desc(SystemPaperPosition.open_time), desc(SystemPaperPosition.id))))
    return {"symbol": clean, "paper_only": True, "items": [{"id": row.id, "status": row.status, "direction": row.direction, "quantity": _value(row.quantity), "average_entry": _value(row.average_entry), "current_price": _value(row.current_price), "unrealized_pnl": _value(row.unrealized_pnl), "realized_pnl": _value(row.realized_pnl), "open_time": _value(row.open_time), "close_time": _value(row.close_time)} for row in rows], "total": len(rows)}


@router.get("/signals/recent")
def recent_signals(symbol: str = None, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = select(CandidateSignal)
    if symbol:
        clean = symbol.upper().replace("US.", "")
        query = query.where(CandidateSignal.symbol.in_([clean, "US." + clean]))
    rows = list(db.scalars(query.order_by(desc(CandidateSignal.bar_timestamp), desc(CandidateSignal.id)).limit(limit)))
    return {"items": [{"id": row.id, "symbol": row.symbol, "market": row.market, "timeframe": row.timeframe, "signal_type": row.signal_type, "score": row.score, "confidence": row.confidence, "status": row.status, "bar_timestamp": _value(row.bar_timestamp), "strategy": row.strategy_name, "strategy_version": row.strategy_version} for row in rows], "total": len(rows), "limit": limit}
