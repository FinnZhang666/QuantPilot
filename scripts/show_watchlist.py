#!/usr/bin/env python3
import argparse

from app.database.session import get_session_factory
from app.strategy.watchlist import WatchlistService


def main() -> int:
    parser = argparse.ArgumentParser(description="查看观察池")
    parser.add_argument("--enabled-only", action="store_true")
    parser.add_argument("--role")
    parser.add_argument("--validation-status")
    args = parser.parse_args()
    with get_session_factory()() as db:
        rows = WatchlistService(db).list_symbols(
            args.enabled_only, args.role, args.validation_status,
        )
        print("Ticker\t类型\t行业\t角色\tBenchmark\t模板\t启用\t验证\t分类来源")
        for item in rows:
            print("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (
                item.symbol, item.asset_type, item.sector, item.role,
                item.benchmark_symbol or "-", item.strategy_template,
                "是" if item.enabled else "否", item.validation_status,
                item.classification_source,
            ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
