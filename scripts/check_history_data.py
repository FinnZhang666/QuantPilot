#!/usr/bin/env python3
import argparse

from sqlalchemy import func, select

from app.database.models import HistoryDataIssue, MarketBar
from app.database.session import get_session_factory
from app.historical.quality import HistoricalDataQualityService


def main() -> int:
    parser = argparse.ArgumentParser(description="历史行情数据质量检查")
    parser.add_argument("--symbols", nargs="+", required=True)
    args = parser.parse_args()
    print("历史数据质量检查")
    with get_session_factory()() as db:
        for symbol in [item.upper() for item in args.symbols]:
            intervals = db.scalars(select(MarketBar.interval).where(MarketBar.symbol == symbol).distinct())
            for interval in intervals:
                scan = HistoricalDataQualityService(db).scan(symbol, interval)
                count, earliest, latest = db.execute(
                    select(func.count(MarketBar.id), func.min(MarketBar.timestamp_utc), func.max(MarketBar.timestamp_utc))
                    .where(MarketBar.symbol == symbol, MarketBar.interval == interval)
                ).one()
                issues = db.scalar(
                    select(func.count(HistoryDataIssue.id)).where(
                        HistoryDataIssue.symbol == symbol, HistoryDataIssue.interval == interval
                    )
                )
                print(f"{symbol} {interval}：")
                print(f"- 数据条数：{count}")
                print(f"- 最早时间：{earliest}")
                print(f"- 最新时间：{latest}")
                print(f"- 数据问题：{issues}")
                print(f"- OHLC异常：{scan['INVALID_OHLC']}")
                print(f"- 时间异常：{scan['TIME_ORDER_ERROR']}")
                print(f"- 明显缺口警告：{scan['LARGE_GAP']}")
                print(f"- 状态：{'正常' if not issues else '需要检查'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
