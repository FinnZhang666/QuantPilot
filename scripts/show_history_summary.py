#!/usr/bin/env python3
from sqlalchemy import desc, func, select

from app.database.models import HistoryDataIssue, HistorySyncJob, MarketBar
from app.database.session import get_session_factory


def main() -> int:
    print("历史行情数据摘要")
    with get_session_factory()() as db:
        rows = db.execute(
            select(
                MarketBar.symbol,
                MarketBar.interval,
                func.count(MarketBar.id),
                func.min(MarketBar.timestamp_utc),
                func.max(MarketBar.timestamp_utc),
            ).group_by(MarketBar.symbol, MarketBar.interval)
        )
        for symbol, interval, count, earliest, latest in rows:
            job = db.scalar(
                select(HistorySyncJob)
                .where(HistorySyncJob.symbol == symbol, HistorySyncJob.interval == interval)
                .order_by(desc(HistorySyncJob.id))
                .limit(1)
            )
            issues = db.scalar(
                select(func.count(HistoryDataIssue.id)).where(
                    HistoryDataIssue.symbol == symbol, HistoryDataIssue.interval == interval
                )
            )
            print(
                f"{symbol} {interval}：{count}条，{earliest} 至 {latest}，"
                f"最近同步={job.status if job else '无'}，问题={issues}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
