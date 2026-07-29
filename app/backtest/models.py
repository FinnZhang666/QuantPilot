from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional


class RunMode(str, Enum):
    SIGNAL_REPLAY = "SIGNAL_REPLAY"
    STRATEGY_RECOMPUTE = "STRATEGY_RECOMPUTE"


class PositionState(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"


class ActionType(str, Enum):
    ENTER_LONG_PENDING = "ENTER_LONG_PENDING"
    EXIT_LONG_PENDING = "EXIT_LONG_PENDING"


@dataclass(frozen=True)
class BacktestBar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class BacktestSignal:
    timestamp: datetime
    signal_type: str
    parameters_hash: str


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    parameters_hash: str
    initial_cash: Decimal = Decimal("100000")
    commission_per_trade: Decimal = Decimal("0")
    commission_per_share: Decimal = Decimal("0")
    minimum_commission: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("0")
    force_close_at_end: bool = True
    run_mode: RunMode = RunMode.SIGNAL_REPLAY


@dataclass
class PendingAction:
    action_type: ActionType
    signal_timestamp: datetime
    signal_type: str
    scheduled_execution_timestamp: Optional[datetime]
    status: str = "PENDING"
    failure_reason: Optional[str] = None


@dataclass
class TradeResult:
    trade_number: int
    status: str
    entry_signal_timestamp: datetime
    entry_execution_timestamp: datetime
    entry_signal_type: str
    entry_raw_price: Decimal
    entry_adjusted_price: Decimal
    entry_shares: int
    entry_notional: Decimal
    entry_fees: Decimal
    exit_signal_timestamp: Optional[datetime] = None
    exit_execution_timestamp: Optional[datetime] = None
    exit_signal_type: Optional[str] = None
    exit_reason: Optional[str] = None
    exit_raw_price: Optional[Decimal] = None
    exit_adjusted_price: Optional[Decimal] = None
    exit_notional: Optional[Decimal] = None
    exit_fees: Optional[Decimal] = None
    gross_pnl: Optional[Decimal] = None
    net_pnl: Optional[Decimal] = None
    return_pct: Optional[Decimal] = None
    holding_bars: Optional[int] = None
    holding_seconds: Optional[int] = None
    mae_pct: Optional[Decimal] = None
    mfe_pct: Optional[Decimal] = None


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    cash: Decimal
    position_shares: int
    position_market_value: Decimal
    equity: Decimal
    running_peak: Decimal
    drawdown_amount: Decimal
    drawdown_pct: Decimal
    signal_type: Optional[str]
    position_state: PositionState


@dataclass
class BacktestResult:
    status: str
    bars_processed: int
    signals_processed: int
    ending_cash: Decimal
    ending_equity: Decimal
    trades: List[TradeResult] = field(default_factory=list)
    equity_points: List[EquityPoint] = field(default_factory=list)
    pending_actions: List[PendingAction] = field(default_factory=list)
    metrics: Dict[str, object] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
