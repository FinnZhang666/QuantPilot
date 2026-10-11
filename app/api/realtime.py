from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import BarInterval, RealtimeDataType, RealtimeServiceState
from app.database.models import RealtimeBar, RealtimeQuote, RealtimeServiceStatus, RealtimeTicker
from app.database.session import get_db
from app.realtime.factory import get_realtime_manager
from app.realtime.manager import STATUS_TEXT
from app.realtime.session import SESSION_TEXT

router = APIRouter(prefix="/realtime", tags=["实时行情"])
ABSOLUTE_LIMIT = 5000


class RealtimeControlRequest(BaseModel):
    symbols: Optional[List[str]] = Field(default=None, max_length=20)
    data_types: List[RealtimeDataType] = Field(default=[
        RealtimeDataType.QUOTE, RealtimeDataType.TICKER,
        RealtimeDataType.KLINE_1M, RealtimeDataType.MARKET_STATE,
    ])


def _time(value: datetime, timezone_name: str) -> str:
    source = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return source.astimezone(ZoneInfo(timezone_name)).isoformat()


def _validate_timezone(timezone_name: str) -> None:
    try:
        ZoneInfo(timezone_name)
    except Exception:
        raise HTTPException(422, "时区名称无效。")


def _health_payload(manager):
    value = manager.get_status()
    return {
        "status": value.status, "status_text": STATUS_TEXT.get(value.status, "未知状态"),
        "opend_connected": value.opend_connected,
        "market_session": value.current_session.value,
        "market_session_text": SESSION_TEXT[value.current_session],
        "subscribed_symbol_count": value.subscribed_symbol_count,
        "subscribed_types": sorted(item.value for item in value.subscribed_types),
        "queue_size": value.queue_size, "queue_capacity": value.queue_capacity,
        "received_count": value.received_count, "persisted_count": value.persisted_count,
        "received_by_type": manager.received_by_type,
        "duplicate_count": value.duplicate_count, "dropped_count": value.dropped_count,
        "error_count": value.error_count, "reconnect_count": value.reconnect_count,
        "last_message_at": value.last_message_at, "warnings": value.warnings,
    }


@router.get("/status")
def realtime_status(db: Session = Depends(get_db)):
    row = db.scalar(select(RealtimeServiceStatus).where(RealtimeServiceStatus.service_name == "moomoo_realtime"))
    if row is None:
        return {"status": "STOPPED", "status_text": "已停止"}
    return {"status": row.status, "status_text": STATUS_TEXT.get(row.status, "未知状态"), "updated_at": row.updated_at, "metadata": row.metadata_json}


@router.get("/health")
def realtime_health(db: Session = Depends(get_db)):
    manager = get_realtime_manager()
    if manager.status != RealtimeServiceState.STOPPED:
        return _health_payload(manager)
    row = db.scalar(select(RealtimeServiceStatus).where(
        RealtimeServiceStatus.service_name == "moomoo_realtime",
    ))
    if row is None or row.status == RealtimeServiceState.STOPPED.value:
        return _health_payload(manager)
    metadata = row.metadata_json or {}
    return {
        "status": row.status, "status_text": STATUS_TEXT.get(row.status, "未知状态"),
        "opend_connected": row.status == RealtimeServiceState.CONNECTED.value,
        "market_session": metadata.get("market_session", "UNKNOWN"),
        "market_session_text": metadata.get("market_session_text", "未知"),
        "subscribed_symbol_count": len(row.subscribed_symbols_json or []),
        "subscribed_types": row.subscribed_types_json or [],
        "queue_size": metadata.get("queue_size", 0),
        "queue_capacity": metadata.get("queue_capacity", 0),
        "received_count": metadata.get("received", 0),
        "persisted_count": metadata.get("persisted", 0),
        "received_by_type": metadata.get("received_by_type", {}),
        "duplicate_count": metadata.get("duplicates", 0),
        "dropped_count": metadata.get("dropped", 0),
        "error_count": metadata.get("errors", 0),
        "reconnect_count": row.reconnect_count,
        "last_message_at": row.last_message_at,
        "warnings": [metadata.get("warning")] if metadata.get("warning") else [],
        "source": "persisted_runtime_status",
    }


@router.get("/subscriptions")
def realtime_subscriptions():
    manager = get_realtime_manager()
    return [{"symbol": symbol, "data_types": sorted(item.value for item in types)} for symbol, types in sorted(manager.subscriptions.items())]


@router.get("/quotes/latest")
def latest_quotes(symbols: Optional[str] = None, timezone_name: str = Query("UTC", alias="timezone"), db: Session = Depends(get_db)):
    _validate_timezone(timezone_name)
    requested = [item.strip().upper() for item in symbols.split(",")] if symbols else []
    if not requested:
        status = db.scalar(select(RealtimeServiceStatus).where(
            RealtimeServiceStatus.service_name == "moomoo_realtime",
        ))
        requested = list(status.subscribed_symbols_json or []) if status else []
    requested = list(dict.fromkeys(requested))[:20]
    rows = []
    for symbol in requested:
        row = db.scalar(select(RealtimeQuote).where(
            RealtimeQuote.symbol == symbol,
        ).order_by(desc(RealtimeQuote.timestamp_utc), desc(RealtimeQuote.id)).limit(1))
        if row is not None:
            rows.append(row)
    result = []
    for row in rows:
        previous = float(row.prev_close) if row.prev_close else None
        last = float(row.last_price)
        change_pct = ((last / previous) - 1) * 100 if previous else None
        result.append({
            "symbol": row.symbol, "timestamp": _time(row.timestamp_utc, timezone_name),
            "last_price": str(row.last_price),
            "change_pct": None if change_pct is None else round(change_pct, 4),
            "open": None if row.open_price is None else str(row.open_price),
            "high": None if row.high_price is None else str(row.high_price),
            "low": None if row.low_price is None else str(row.low_price),
            "volume": row.volume,
            "bid": None if row.bid_price is None else str(row.bid_price),
            "ask": None if row.ask_price is None else str(row.ask_price),
            "market_session": row.market_session,
            "market_session_text": SESSION_TEXT.get(row.market_session, "未知"),
        })
    return result


@router.get("/tickers")
def realtime_tickers(symbol: str, start: Optional[datetime] = None, end: Optional[datetime] = None, limit: int = Query(1000, ge=1, le=ABSOLUTE_LIMIT), timezone_name: str = Query("UTC", alias="timezone"), db: Session = Depends(get_db)):
    _validate_timezone(timezone_name)
    query = select(RealtimeTicker).where(RealtimeTicker.symbol == symbol.upper())
    if start:
        query = query.where(RealtimeTicker.ticker_time_utc >= start)
    if end:
        query = query.where(RealtimeTicker.ticker_time_utc <= end)
    rows = db.scalars(query.order_by(desc(RealtimeTicker.ticker_time_utc)).limit(limit))
    return [{"symbol": row.symbol, "time": _time(row.ticker_time_utc, timezone_name), "price": str(row.price), "volume": row.volume, "direction": row.direction, "sequence": row.sequence} for row in rows]


@router.get("/bars")
def realtime_bars(symbol: str, interval: BarInterval = BarInterval.MIN_1, start: Optional[datetime] = None, end: Optional[datetime] = None, limit: int = Query(1000, ge=1, le=ABSOLUTE_LIMIT), timezone_name: str = Query("UTC", alias="timezone"), closed_only: bool = False, db: Session = Depends(get_db)):
    _validate_timezone(timezone_name)
    if interval != BarInterval.MIN_1:
        raise HTTPException(422, "Sprint 03实时K线仅支持1m。")
    query = select(RealtimeBar).where(RealtimeBar.symbol == symbol.upper(), RealtimeBar.interval == "1m")
    if start:
        query = query.where(RealtimeBar.timestamp_utc >= start)
    if end:
        query = query.where(RealtimeBar.timestamp_utc <= end)
    if closed_only:
        query = query.where(RealtimeBar.is_closed.is_(True))
    rows = db.scalars(query.order_by(desc(RealtimeBar.timestamp_utc)).limit(limit))
    return [{"symbol": row.symbol, "interval": row.interval, "time": _time(row.timestamp_utc, timezone_name), "open": str(row.open), "high": str(row.high), "low": str(row.low), "close": str(row.close), "volume": row.volume, "is_closed": row.is_closed} for row in rows]


@router.post("/start")
def start_realtime(request: RealtimeControlRequest, settings: Settings = Depends(get_settings)):
    manager = get_realtime_manager(settings)
    if request.symbols and manager.status == RealtimeServiceState.STOPPED:
        manager.requested_symbols = list(dict.fromkeys(item.upper() for item in request.symbols))
    if manager.status == RealtimeServiceState.STOPPED:
        manager.requested_types = set(request.data_types)
    result = manager.start()
    return {"status": manager.status.value, "status_text": STATUS_TEXT[manager.status.value], "successful": result.successful, "failed": result.failed, "skipped": result.skipped}


@router.post("/stop")
def stop_realtime():
    manager = get_realtime_manager()
    result = manager.stop()
    return {"status": manager.status.value, "status_text": "已安全停止并刷新队列", "successful": result.successful}


@router.post("/subscribe")
def subscribe(request: RealtimeControlRequest):
    if not request.symbols:
        raise HTTPException(422, "必须明确指定订阅标的。")
    manager = get_realtime_manager()
    if manager.provider is None:
        raise HTTPException(409, "实时服务尚未启动。")
    result = manager.subscribe_symbols(request.symbols, request.data_types)
    return {"status_text": "订阅处理完成", "successful": result.successful, "failed": result.failed, "skipped": result.skipped}


@router.post("/unsubscribe")
def unsubscribe(request: RealtimeControlRequest):
    if not request.symbols:
        raise HTTPException(422, "必须明确指定取消订阅标的。")
    result = get_realtime_manager().unsubscribe_symbols(request.symbols, request.data_types)
    return {"status_text": "取消订阅处理完成", "successful": result.successful, "failed": result.failed, "skipped": result.skipped}
