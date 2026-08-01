from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.models import (
    SystemEquitySnapshot,
    SystemPaperAccount,
    SystemPaperAuditEvent,
    SystemPaperFill,
    SystemPaperOrder,
    SystemPaperPosition,
    TradePlan,
    TradeReview,
)
from app.database.session import get_db
from app.paper_runtime.manager import get_runtime_manager
from app.paper_runtime.performance import PaperPerformanceService
from app.paper_runtime.review import SystemPaperReviewService
from app.paper_runtime.schemas import (
    AccountResponse,
    ActionResponse,
    AuditListResponse,
    DryRunRequest,
    EquityResponse,
    FillListResponse,
    ManualCloseRequest,
    OrderListResponse,
    PerformanceResponse,
    PositionDetailResponse,
    PositionListResponse,
    RunOnceRequest,
    RuntimeResponse,
    SchedulerResponse,
    ScoreboardResponse,
)
from app.paper_runtime.service import PaperTradingService


router = APIRouter(
    prefix="/api/system-paper", tags=["System Paper Trading"],
    dependencies=[Depends(require_read)],
)
internal_router = APIRouter(
    prefix="/internal/system-paper", tags=["Internal System Paper Trading"],
    dependencies=[Depends(require_admin)], include_in_schema=False,
)


def text(value):
    rendered = format(Decimal(str(value if value is not None else 0)), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def optional_text(value):
    return None if value is None else text(value)


@router.get("/account", response_model=AccountResponse)
def account(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    row = db.scalar(select(SystemPaperAccount).where(
        SystemPaperAccount.account_key == "system-paper",
    ))
    if row is None:
        initial = text(settings.paper_trading_initial_cash)
        return {
            "account_key": "system-paper", "base_currency": "USD",
            "initial_cash": initial, "available_cash": initial, "reserved_cash": "0",
            "position_market_value": "0", "total_equity": initial,
            "realized_pnl": "0", "unrealized_pnl": "0", "daily_pnl": "0",
            "total_return": "0", "peak_equity": initial, "max_drawdown": "0",
            "last_valuation_at": None, "status": "NOT_INITIALIZED", "paper_only": True,
        }
    return _account(row)


@router.get("/positions", response_model=PositionListResponse)
def positions(
    status: Optional[str] = None, strategy: Optional[str] = None,
    symbol: Optional[str] = None, direction: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(SystemPaperPosition)
    count_query = select(func.count()).select_from(SystemPaperPosition)
    filters = []
    if status:
        filters.append(SystemPaperPosition.status == status.upper())
    if strategy:
        filters.append(SystemPaperPosition.strategy_name == strategy)
    if symbol:
        filters.append(SystemPaperPosition.symbol == symbol.upper().replace("US.", ""))
    if direction:
        filters.append(SystemPaperPosition.direction == direction.upper())
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    rows = list(db.scalars(query.order_by(
        desc(SystemPaperPosition.open_time), desc(SystemPaperPosition.id),
    ).offset(offset).limit(limit)))
    reviews = _review_map(db, rows)
    return {
        "items": [_position(row, reviews.get(row.id)) for row in rows],
        "total": int(db.scalar(count_query) or 0), "limit": limit, "offset": offset,
    }


@router.get("/positions/{position_id}", response_model=PositionDetailResponse)
def position_detail(position_id: int, db: Session = Depends(get_db)):
    row = db.get(SystemPaperPosition, position_id)
    if row is None:
        raise HTTPException(404, "System paper position not found.")
    plan = db.get(TradePlan, row.trade_plan_id)
    review = db.scalar(select(TradeReview).where(
        TradeReview.system_paper_position_id == row.id,
    ).order_by(desc(TradeReview.id)).limit(1))
    orders = list(db.scalars(select(SystemPaperOrder).where(
        SystemPaperOrder.trade_plan_id == row.trade_plan_id,
    ).order_by(SystemPaperOrder.created_at, SystemPaperOrder.id)))
    order_ids = [item.id for item in orders]
    fills = list(db.scalars(select(SystemPaperFill).where(
        SystemPaperFill.order_id.in_(order_ids),
    ).order_by(SystemPaperFill.timestamp, SystemPaperFill.id))) if order_ids else []
    data = _position(row, review.id if review else None)
    data.update({
        "candidate_id": plan.signal_id if plan else None,
        "opening_order_id": row.opening_order_id,
        "closing_order_id": row.closing_order_id,
        "entry_bar_timestamp": row.entry_bar_timestamp,
        "last_market_timestamp": row.last_market_timestamp,
        "last_exit_trigger_price": optional_text(row.last_exit_trigger_price),
        "last_exit_trigger_bar": row.last_exit_trigger_bar,
        "fill_model_version": row.fill_model_version,
        "exit_rule_version": row.exit_rule_version,
        "trace": {
            "candidate_id": plan.signal_id if plan else None,
            "trade_plan_id": row.trade_plan_id,
            "order_ids": order_ids,
            "fill_ids": [item.id for item in fills],
            "position_id": row.id,
            "review_id": review.id if review else None,
        },
    })
    return data


@router.get("/orders", response_model=OrderListResponse)
def orders(
    status: Optional[str] = None, symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(SystemPaperOrder)
    count_query = select(func.count()).select_from(SystemPaperOrder)
    filters = []
    if status:
        filters.append(SystemPaperOrder.status == status.upper())
    if symbol:
        filters.append(SystemPaperOrder.symbol == symbol.upper().replace("US.", ""))
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    rows = list(db.scalars(query.order_by(
        desc(SystemPaperOrder.created_at), desc(SystemPaperOrder.id),
    ).offset(offset).limit(limit)))
    return {
        "items": [_order(row) for row in rows],
        "total": int(db.scalar(count_query) or 0), "limit": limit, "offset": offset,
    }


@router.get("/fills", response_model=FillListResponse)
def fills(
    order_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(SystemPaperFill)
    count_query = select(func.count()).select_from(SystemPaperFill)
    if order_id is not None:
        query = query.where(SystemPaperFill.order_id == order_id)
        count_query = count_query.where(SystemPaperFill.order_id == order_id)
    rows = list(db.scalars(query.order_by(
        desc(SystemPaperFill.timestamp), desc(SystemPaperFill.id),
    ).offset(offset).limit(limit)))
    return {
        "items": [{
            "id": row.id, "order_id": row.order_id, "price": text(row.price),
            "quantity": text(row.quantity), "timestamp": row.timestamp,
            "bar_timestamp": row.bar_timestamp, "slippage": text(row.slippage),
            "fee": text(row.fee), "source": row.source,
        } for row in rows],
        "total": int(db.scalar(count_query) or 0), "limit": limit, "offset": offset,
    }


@router.get("/equity", response_model=EquityResponse)
def equity(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(SystemEquitySnapshot).order_by(
        SystemEquitySnapshot.timestamp, SystemEquitySnapshot.id,
    )))
    return {"items": [{
        "timestamp": row.timestamp, "cash": text(row.cash),
        "reserved_cash": text(row.reserved_cash),
        "position_value": text(row.position_value), "equity": text(row.equity),
        "daily_pnl": text(row.daily_pnl), "daily_return": text(row.daily_return),
        "total_return": text(row.total_return),
        "cumulative_return": text(row.cumulative_return),
        "peak_equity": text(row.peak_equity), "drawdown": text(row.drawdown),
        "max_drawdown": text(row.max_drawdown), "source": row.source,
    } for row in rows], "total": len(rows)}


@router.get("/performance", response_model=PerformanceResponse)
def performance(
    strategy: Optional[str] = None, strategy_version: Optional[str] = None,
    symbol: Optional[str] = None, market: Optional[str] = None,
    timeframe: Optional[str] = None, direction: Optional[str] = None,
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    service = PaperPerformanceService(db)
    rows = service.positions(
        strategy, strategy_version, symbol, market, timeframe, direction,
        date_from, date_to,
    )
    return _performance(service.performance(rows))


@router.get("/scoreboard", response_model=ScoreboardResponse)
def scoreboard(
    strategy: Optional[str] = None, strategy_version: Optional[str] = None,
    symbol: Optional[str] = None, market: Optional[str] = None,
    timeframe: Optional[str] = None, direction: Optional[str] = None,
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    service = PaperPerformanceService(db)
    rows = service.positions(
        strategy, strategy_version, symbol, market, timeframe, direction,
        date_from, date_to,
    )
    items = []
    for item in service.scoreboard(rows):
        items.append({
            **_performance(item), "strategy": item["strategy"],
            "strategy_version": item["strategy_version"],
        })
    return {"items": items, "total": len(items), "source": "SYSTEM_PAPER_ONLY"}


@router.get("/runtime", response_model=RuntimeResponse)
def runtime_status():
    return get_runtime_manager().snapshot()


@router.get("/scheduler", response_model=SchedulerResponse)
def scheduler_status():
    return get_runtime_manager().scheduler.status()


@router.get("/audit", response_model=AuditListResponse)
def audit_events(
    event_type: Optional[str] = None, position_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(SystemPaperAuditEvent)
    count_query = select(func.count()).select_from(SystemPaperAuditEvent)
    filters = []
    if event_type:
        filters.append(SystemPaperAuditEvent.event_type == event_type.upper())
    if position_id is not None:
        filters.append(SystemPaperAuditEvent.position_id == position_id)
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    rows = list(db.scalars(query.order_by(
        desc(SystemPaperAuditEvent.timestamp), desc(SystemPaperAuditEvent.id),
    ).offset(offset).limit(limit)))
    return {
        "items": [{
            "id": row.id, "event_type": row.event_type, "timestamp": row.timestamp,
            "candidate_id": row.candidate_id, "trade_plan_id": row.trade_plan_id,
            "order_id": row.order_id, "fill_id": row.fill_id,
            "position_id": row.position_id, "review_id": row.review_id,
            "correlation_id": row.correlation_id, "details": row.details_json,
        } for row in rows],
        "total": int(db.scalar(count_query) or 0), "limit": limit, "offset": offset,
    }


# Legacy admin aliases are retained but intentionally excluded from public OpenAPI.
@router.post("/runtime/start", include_in_schema=False)
def runtime_start(_admin=Depends(require_admin)):
    return get_runtime_manager().start()


@router.post("/runtime/stop", include_in_schema=False)
def runtime_stop(_admin=Depends(require_admin)):
    return get_runtime_manager().stop()


@router.post("/runtime/process-once", include_in_schema=False)
def runtime_process_once(
    max_entries: int = Query(3, ge=1, le=3), _admin=Depends(require_admin),
):
    return get_runtime_manager().process_once(max_entries=max_entries)


@internal_router.post("/start", response_model=ActionResponse)
def internal_start():
    result = get_runtime_manager().start()
    return {"status": result["status"], "result": result}


@internal_router.post("/stop", response_model=ActionResponse)
def internal_stop():
    result = get_runtime_manager().stop()
    return {"status": result["status"], "result": result}


@internal_router.post("/run-once", response_model=ActionResponse)
def internal_run_once(request: RunOnceRequest):
    result = get_runtime_manager().process_once(max_entries=request.max_entries)
    return {"status": result.get("status", "SUCCESS"), "result": result}


@internal_router.post("/dry-run", response_model=ActionResponse)
def internal_dry_run(request: DryRunRequest):
    result = get_runtime_manager().dry_run(max_entries=request.max_entries)
    return {"status": result["status"], "result": result}


@internal_router.post("/positions/{position_id}/close", response_model=ActionResponse)
def internal_close(
    position_id: int, request: ManualCloseRequest,
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
):
    try:
        quantity = Decimal(request.quantity) if request.quantity is not None else None
        row = PaperTradingService(db, settings).manual_close(
            position_id, request.reason, quantity,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc))
    return {"status": "SUCCESS", "result": {"position_id": row.id, "position_status": row.status}}


@internal_router.post("/revalue", response_model=ActionResponse)
def internal_revalue(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
):
    service = PaperTradingService(db, settings)
    row = service.account()
    service.value_account(row, source="MANUAL_REVALUE")
    db.commit()
    return {"status": "SUCCESS", "result": _account(row)}


@internal_router.post("/reviews/generate", response_model=ActionResponse)
def internal_generate_reviews(db: Session = Depends(get_db)):
    result = SystemPaperReviewService(db).generate_pending(limit=100)
    return {"status": result["status"], "result": result}


def _account(row):
    return {
        "account_key": row.account_key, "base_currency": row.base_currency,
        "initial_cash": text(row.initial_cash), "available_cash": text(row.available_cash),
        "reserved_cash": text(row.reserved_cash),
        "position_market_value": text(row.position_market_value),
        "total_equity": text(row.total_equity), "realized_pnl": text(row.realized_pnl),
        "unrealized_pnl": text(row.unrealized_pnl), "daily_pnl": text(row.daily_pnl),
        "total_return": text(row.total_return), "peak_equity": text(row.peak_equity),
        "max_drawdown": text(row.max_drawdown),
        "last_valuation_at": row.last_valuation_at, "status": row.status, "paper_only": True,
    }


def _position(row, review_id=None):
    initial = Decimal(str(row.average_entry)) * Decimal(str(row.initial_quantity or 0))
    pnl = Decimal(str(row.realized_pnl if row.status == "CLOSED" else row.unrealized_pnl))
    return_value = pnl / initial if initial else Decimal("0")
    end = row.close_time or datetime.now(timezone.utc)
    opened = row.open_time.replace(tzinfo=timezone.utc) if row.open_time.tzinfo is None else row.open_time
    ended = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end
    return {
        "id": row.id, "trade_plan_id": row.trade_plan_id,
        "symbol": row.symbol, "market": row.market, "direction": row.direction,
        "strategy": row.strategy_name, "strategy_version": row.strategy_version,
        "trade_style": row.trade_style, "timeframe": row.timeframe,
        "quantity": text(row.quantity), "initial_quantity": text(row.initial_quantity),
        "average_entry": text(row.average_entry), "current_price": text(row.current_price),
        "market_value": text(row.market_value), "unrealized_pnl": text(row.unrealized_pnl),
        "realized_pnl": text(row.realized_pnl), "return_value": text(return_value),
        "mfe": text(row.mfe), "mae": text(row.mae),
        "stop": optional_text(row.stop_price), "targets": row.targets_json or [],
        "target_index": row.target_index, "status": row.status,
        "market_data_status": row.market_data_status, "data_quality": row.data_quality,
        "open_time": row.open_time, "close_time": row.close_time,
        "holding_minutes": max(0, int((ended - opened).total_seconds() // 60)),
        "exit_price": optional_text(row.exit_price), "exit_reason": row.exit_reason,
        "review_id": review_id,
    }


def _order(row):
    return {
        "id": row.id, "trade_plan_id": row.trade_plan_id,
        "symbol": row.symbol, "market": row.market,
        "strategy": row.strategy_name, "strategy_version": row.strategy_version,
        "direction": row.direction, "side": row.order_side, "type": row.order_type,
        "requested_price": text(row.requested_price),
        "trigger_price": optional_text(row.trigger_price),
        "trigger_bar_timestamp": row.trigger_bar_timestamp,
        "quantity": text(row.quantity), "status": row.status,
        "rejection_code": row.rejection_code,
        "fill_model_version": row.fill_model_version, "rule_version": row.rule_version,
        "created_at": row.created_at, "filled_at": row.filled_at,
    }


def _review_map(db, rows):
    ids = [row.id for row in rows]
    if not ids:
        return {}
    values = list(db.execute(select(
        TradeReview.system_paper_position_id, TradeReview.id,
    ).where(TradeReview.system_paper_position_id.in_(ids))))
    return {position_id: review_id for position_id, review_id in values}


def _performance(item):
    return {
        "trade_count": item["trade_count"], "closed_trades": item["closed_trades"],
        "open_trades": item["open_trades"], "wins": item["wins"],
        "losses": item["losses"], "breakeven": item["breakeven"],
        "win_rate": text(item["win_rate"]), "average_return": text(item["average_return"]),
        "average_win": text(item["average_win"]), "average_loss": text(item["average_loss"]),
        "profit_factor": optional_text(item["profit_factor"]),
        "expectancy": text(item["expectancy"]), "average_mfe": text(item["average_mfe"]),
        "average_mae": text(item["average_mae"]),
        "average_holding_minutes": text(item["average_holding_minutes"]),
        "total_realized_pnl": text(item["total_realized_pnl"]),
        "total_return": text(item["total_return"]),
        "maximum_drawdown": text(item["maximum_drawdown"]),
        "current_exposure": text(item["current_exposure"]),
        "sample_size": item["sample_size"], "sharpe": None,
        "recent_30_trades": [{
            **recent, "return": text(recent["return"]),
            "realized_pnl": text(recent["realized_pnl"]),
        } for recent in item["recent_30_trades"]],
        "source": "SYSTEM_PAPER_ONLY",
    }
