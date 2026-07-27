from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import BarInterval
from app.database.models import HistoryDataIssue, MarketBar

INTERVAL_MINUTES = {
    BarInterval.MIN_1.value: 1,
    BarInterval.MIN_5.value: 5,
    BarInterval.MIN_15.value: 15,
    BarInterval.MIN_30.value: 30,
    BarInterval.HOUR_1.value: 60,
}


class HistoricalDataQualityService:
    def __init__(self, db: Session):
        self.db = db

    def scan(self, symbol: str, interval: str) -> Dict[str, int]:
        rows = list(
            self.db.scalars(
                select(MarketBar)
                .where(MarketBar.symbol == symbol, MarketBar.interval == interval)
                .order_by(MarketBar.timestamp_utc)
            )
        )
        counts = {"INVALID_OHLC": 0, "NEGATIVE_VOLUME": 0, "TIME_ORDER_ERROR": 0, "LARGE_GAP": 0}
        previous: Optional[MarketBar] = None
        for row in rows:
            if row.high < max(row.open, row.close) or row.low > min(row.open, row.close) or row.high < row.low:
                self._issue(row, "INVALID_OHLC", "OHLC关系无效", "ERROR")
                counts["INVALID_OHLC"] += 1
            if row.volume < 0:
                self._issue(row, "NEGATIVE_VOLUME", "成交量为负数", "ERROR")
                counts["NEGATIVE_VOLUME"] += 1
            if previous and row.timestamp_utc <= previous.timestamp_utc:
                self._issue(row, "TIME_ORDER_ERROR", "时间顺序异常", "ERROR")
                counts["TIME_ORDER_ERROR"] += 1
            minutes = INTERVAL_MINUTES.get(interval)
            if (
                previous
                and minutes
                and row.trading_date == previous.trading_date
                and row.market_session == previous.market_session
                and row.timestamp_utc - previous.timestamp_utc > timedelta(minutes=minutes * 5)
            ):
                self._issue(
                    row,
                    "LARGE_GAP",
                    "同一交易日和时段内存在明显时间缺口，需人工确认",
                    "WARNING",
                )
                counts["LARGE_GAP"] += 1
            previous = row
        self.db.commit()
        return counts

    def _issue(self, row: MarketBar, issue_type: str, message: str, severity: str) -> None:
        exists = self.db.scalar(
            select(HistoryDataIssue.id).where(
                HistoryDataIssue.symbol == row.symbol,
                HistoryDataIssue.interval == row.interval,
                HistoryDataIssue.timestamp_utc == row.timestamp_utc,
                HistoryDataIssue.issue_type == issue_type,
                HistoryDataIssue.resolved_at.is_(None),
            )
        )
        if exists is None:
            self.db.add(
                HistoryDataIssue(
                    symbol=row.symbol,
                    interval=row.interval,
                    timestamp_utc=row.timestamp_utc,
                    issue_type=issue_type,
                    severity=severity,
                    message=message,
                )
            )
