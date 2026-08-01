from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import SystemEquitySnapshot, SystemPaperAccount, SystemPaperPosition


D = Decimal


class PaperPerformanceService:
    """Read-only performance calculations from system paper facts, never AI text."""

    def __init__(self, db: Session):
        self.db = db

    def positions(
        self, strategy: Optional[str] = None, strategy_version: Optional[str] = None,
        symbol: Optional[str] = None, market: Optional[str] = None,
        timeframe: Optional[str] = None, direction: Optional[str] = None,
        date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    ) -> List[SystemPaperPosition]:
        query = select(SystemPaperPosition)
        if strategy:
            query = query.where(SystemPaperPosition.strategy_name == strategy)
        if strategy_version:
            query = query.where(SystemPaperPosition.strategy_version == strategy_version)
        if symbol:
            query = query.where(SystemPaperPosition.symbol == symbol.upper().replace("US.", ""))
        if market:
            query = query.where(SystemPaperPosition.market == market.upper())
        if timeframe:
            query = query.where(SystemPaperPosition.timeframe == timeframe)
        if direction:
            query = query.where(SystemPaperPosition.direction == direction.upper())
        if date_from:
            query = query.where(SystemPaperPosition.open_time >= date_from)
        if date_to:
            query = query.where(SystemPaperPosition.open_time <= date_to)
        return list(self.db.scalars(query.order_by(
            SystemPaperPosition.open_time, SystemPaperPosition.id,
        )))

    def performance(self, rows: Optional[Iterable[SystemPaperPosition]] = None) -> Dict[str, object]:
        items = list(rows) if rows is not None else self.positions()
        closed = [row for row in items if row.status == "CLOSED"]
        open_rows = [row for row in items if row.status == "OPEN"]
        returns = [self.position_return(row) for row in closed]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        breakeven = len(returns) - len(wins) - len(losses)
        pnl_values = [D(str(row.realized_pnl)) for row in closed]
        gross_profit = sum((value for value in pnl_values if value > 0), D("0"))
        gross_loss = abs(sum((value for value in pnl_values if value < 0), D("0")))
        holding = [
            max(0, int((row.close_time - row.open_time).total_seconds() // 60))
            for row in closed if row.close_time is not None
        ]
        account = self.db.scalar(select(SystemPaperAccount).where(
            SystemPaperAccount.account_key == "system-paper",
        ))
        max_drawdown = self.db.scalar(select(func.min(SystemEquitySnapshot.drawdown)))
        return {
            "trade_count": len(items), "closed_trades": len(closed),
            "open_trades": len(open_rows), "wins": len(wins), "losses": len(losses),
            "breakeven": breakeven,
            "win_rate": self._ratio(len(wins), len(closed)),
            "average_return": self._average(returns),
            "average_win": self._average(wins),
            "average_loss": self._average(losses),
            "profit_factor": (gross_profit / gross_loss) if gross_loss else None,
            "expectancy": self._average(returns),
            "average_mfe": self._average([D(str(row.mfe)) for row in closed]),
            "average_mae": self._average([D(str(row.mae)) for row in closed]),
            "average_holding_minutes": self._average(holding),
            "total_realized_pnl": sum(pnl_values, D("0")),
            "total_return": D(str(account.total_return)) if account else D("0"),
            "maximum_drawdown": D(str(max_drawdown or 0)),
            "current_exposure": sum((
                abs(D(str(row.quantity)) * D(str(row.current_price))) for row in open_rows
            ), D("0")),
            "sample_size": len(closed), "sharpe": None,
            "recent_30_trades": [self._recent(row) for row in closed[-30:]],
        }

    def scoreboard(self, rows: Optional[Iterable[SystemPaperPosition]] = None):
        items = list(rows) if rows is not None else self.positions()
        groups = defaultdict(list)
        for row in items:
            groups[(row.strategy_name, row.strategy_version)].append(row)
        result = []
        for (strategy, version), group in sorted(groups.items()):
            stats = self.performance(group)
            stats.update({"strategy": strategy, "strategy_version": version})
            result.append(stats)
        return result

    @staticmethod
    def position_return(row: SystemPaperPosition) -> Decimal:
        quantity = D(str(row.initial_quantity or 0))
        notional = D(str(row.average_entry)) * quantity
        return D(str(row.realized_pnl)) / notional if notional else D("0")

    def _recent(self, row):
        return {
            "position_id": row.id, "symbol": row.symbol,
            "direction": row.direction, "return": self.position_return(row),
            "realized_pnl": D(str(row.realized_pnl)),
            "closed_at": row.close_time, "exit_reason": row.exit_reason,
        }

    @staticmethod
    def _average(values):
        values = list(values)
        return sum((D(str(value)) for value in values), D("0")) / D(len(values)) if values else D("0")

    @staticmethod
    def _ratio(numerator, denominator):
        return D(str(numerator)) / D(str(denominator)) if denominator else D("0")
