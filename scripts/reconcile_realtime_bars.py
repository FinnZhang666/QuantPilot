#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import get_session_factory
from app.realtime.reconcile import RealtimeHistoryReconciler


def main() -> int:
    parser = argparse.ArgumentParser(description="对比实时闭合K线与历史K线")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db = get_session_factory()()
    try:
        service = RealtimeHistoryReconciler(db)
        report = service.compare_range(args.symbol, args.date)
        print("实时与历史K线对账")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.apply:
            print("已显式写入闭合K线：%s条" % service.promote_closed_bars(args.symbol, args.date))
        else:
            print("默认仅检查，未修改历史数据。")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
