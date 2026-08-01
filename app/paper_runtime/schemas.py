from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AccountResponse(BaseModel):
    account_key: str
    base_currency: str
    initial_cash: str
    available_cash: str
    reserved_cash: str
    position_market_value: str
    total_equity: str
    realized_pnl: str
    unrealized_pnl: str
    daily_pnl: str
    total_return: str
    peak_equity: str = "0"
    max_drawdown: str = "0"
    last_valuation_at: Optional[datetime] = None
    status: str
    paper_only: bool = True


class PositionItem(BaseModel):
    id: int
    trade_plan_id: int
    symbol: str
    market: str
    direction: str
    strategy: str
    strategy_version: str
    trade_style: str
    timeframe: str
    quantity: str
    initial_quantity: str
    average_entry: str
    current_price: str
    market_value: str
    unrealized_pnl: str
    realized_pnl: str
    return_value: str
    mfe: str
    mae: str
    stop: Optional[str] = None
    targets: List[Any]
    target_index: int
    status: str
    market_data_status: str
    data_quality: str
    open_time: datetime
    close_time: Optional[datetime] = None
    holding_minutes: int
    exit_price: Optional[str] = None
    exit_reason: Optional[str] = None
    review_id: Optional[int] = None


class PositionListResponse(BaseModel):
    items: List[PositionItem]
    total: int
    limit: int
    offset: int


class PositionDetailResponse(PositionItem):
    candidate_id: Optional[int] = None
    opening_order_id: int
    closing_order_id: Optional[int] = None
    entry_bar_timestamp: Optional[datetime] = None
    last_market_timestamp: Optional[datetime] = None
    last_exit_trigger_price: Optional[str] = None
    last_exit_trigger_bar: Optional[datetime] = None
    fill_model_version: str
    exit_rule_version: str
    trace: Dict[str, Any]


class OrderItem(BaseModel):
    id: int
    trade_plan_id: int
    symbol: str
    market: str
    strategy: str
    strategy_version: str
    direction: str
    side: str
    type: str
    requested_price: str
    trigger_price: Optional[str] = None
    trigger_bar_timestamp: Optional[datetime] = None
    quantity: str
    status: str
    rejection_code: Optional[str] = None
    fill_model_version: str
    rule_version: str
    created_at: datetime
    filled_at: Optional[datetime] = None


class OrderListResponse(BaseModel):
    items: List[OrderItem]
    total: int
    limit: int
    offset: int


class FillItem(BaseModel):
    id: int
    order_id: int
    price: str
    quantity: str
    timestamp: datetime
    bar_timestamp: datetime
    slippage: str
    fee: str
    source: str


class FillListResponse(BaseModel):
    items: List[FillItem]
    total: int
    limit: int
    offset: int


class EquityItem(BaseModel):
    timestamp: datetime
    cash: str
    reserved_cash: str
    position_value: str
    equity: str
    daily_pnl: str
    daily_return: str
    total_return: str
    cumulative_return: str
    peak_equity: str
    drawdown: str
    max_drawdown: str
    source: str


class EquityResponse(BaseModel):
    items: List[EquityItem]
    total: int


class PerformanceResponse(BaseModel):
    trade_count: int
    closed_trades: int
    open_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: str
    average_return: str
    average_win: str
    average_loss: str
    profit_factor: Optional[str] = None
    expectancy: str
    average_mfe: str
    average_mae: str
    average_holding_minutes: str
    total_realized_pnl: str
    total_return: str
    maximum_drawdown: str
    current_exposure: str
    sample_size: int
    sharpe: Optional[str] = None
    recent_30_trades: List[Dict[str, Any]]
    source: str = "SYSTEM_PAPER_ONLY"


class ScoreboardItem(PerformanceResponse):
    strategy: str
    strategy_version: str


class ScoreboardResponse(BaseModel):
    items: List[ScoreboardItem]
    total: int
    source: str = "SYSTEM_PAPER_ONLY"


class RuntimeResponse(BaseModel):
    status: str
    enabled: bool
    paper_trading_enabled: bool
    paper_trading_autostart: bool
    scheduler_enabled: bool
    review_runtime_enabled: bool
    strategy_scoreboard_enabled: bool
    thread_alive: bool
    process_id: int
    lock_owned: bool
    current_task: Optional[str] = None
    last_run_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_result: Dict[str, Any]
    last_error: Optional[str] = None
    error_count: int
    disabled: Optional[bool] = None
    idempotent: Optional[bool] = None
    lock_conflict: Optional[bool] = None


class SchedulerResponse(BaseModel):
    enabled: bool
    non_overlapping: bool
    current_task: Optional[str] = None
    jobs: List[Dict[str, Any]]


class AuditItem(BaseModel):
    id: int
    event_type: str
    timestamp: datetime
    candidate_id: Optional[int] = None
    trade_plan_id: Optional[int] = None
    order_id: Optional[int] = None
    fill_id: Optional[int] = None
    position_id: Optional[int] = None
    review_id: Optional[int] = None
    correlation_id: Optional[str] = None
    details: Dict[str, Any]


class AuditListResponse(BaseModel):
    items: List[AuditItem]
    total: int
    limit: int
    offset: int


class RunOnceRequest(BaseModel):
    max_entries: int = Field(default=3, ge=1, le=3)


class DryRunRequest(BaseModel):
    max_entries: int = Field(default=3, ge=1, le=3)


class ManualCloseRequest(BaseModel):
    reason: str = "MANUAL_CLOSE"
    quantity: Optional[str] = None


class ActionResponse(BaseModel):
    status: str
    result: Dict[str, Any] = Field(default_factory=dict)
