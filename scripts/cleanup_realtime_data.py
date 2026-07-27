#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.realtime.repository import RealtimeRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="清理超过保留期的实时行情数据")
    parser.add_argument("--dry-run", action="store_true", help="仅预览（默认）")
    parser.add_argument("--apply", action="store_true", help="显式执行清理")
    args = parser.parse_args()
    settings = get_settings()
    db = get_session_factory()()
    try:
        counts = RealtimeRepository(db).cleanup_counts(
            settings.realtime_ticker_retention_days,
            settings.realtime_quote_retention_days,
            settings.realtime_bar_retention_days,
            apply=args.apply,
        )
    finally:
        db.close()
    print("实时数据清理" + ("（已执行）" if args.apply else "（预览，不删除）"))
    rules = {"realtime_tickers": settings.realtime_ticker_retention_days, "realtime_quotes": settings.realtime_quote_retention_days, "realtime_bars": settings.realtime_bar_retention_days}
    for table, count in counts.items():
        print("- %s：预计删除%s条，保留%s天" % (table, count, rules[table]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

