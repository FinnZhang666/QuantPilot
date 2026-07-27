#!/usr/bin/env python3
import argparse
from datetime import datetime

from app.database.session import get_session_factory
from app.strategy.service import StrategyRunner


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def main() -> int:
    parser = argparse.ArgumentParser(description="计算候选策略信号")
    parser.add_argument("--symbols", required=True, help="逗号分隔")
    parser.add_argument("--timeframes", required=True, help="逗号分隔")
    parser.add_argument("--mode", choices=["full", "incremental", "range", "realtime"], default="incremental")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--confirm-large-run", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    auto = parser.add_mutually_exclusive_group()
    auto.add_argument("--auto-calculate-features", action="store_true")
    auto.add_argument("--no-auto-calculate-features", action="store_true")
    args = parser.parse_args()
    auto_value = None
    if args.auto_calculate_features:
        auto_value = True
    elif args.no_auto_calculate_features:
        auto_value = False
    try:
        with get_session_factory()() as db:
            result = StrategyRunner(db).run(
                args.symbols.split(","), args.timeframes.split(","), args.mode,
                parse_time(args.start), parse_time(args.end), auto_value,
                args.dry_run, args.confirm_large_run,
            )
        print("候选信号任务结果")
        for key, value in result.items():
            print("%s：%s" % (key, value))
        return 0
    except Exception as exc:
        print("计算失败：%s" % exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
