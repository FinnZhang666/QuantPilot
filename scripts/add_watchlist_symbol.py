#!/usr/bin/env python3
import argparse

from app.database.session import get_session_factory
from app.strategy.watchlist import WatchlistService


def main() -> int:
    parser = argparse.ArgumentParser(description="添加观察Ticker")
    parser.add_argument("symbol")
    parser.add_argument("--market", default="US")
    parser.add_argument("--notes")
    args = parser.parse_args()
    try:
        with get_session_factory()() as db:
            result = WatchlistService(db).add_symbol(args.symbol, args.market, args.notes)
        for key, label in (
            ("symbol", "Ticker"), ("asset_type", "资产类型"), ("sector", "行业"),
            ("role", "角色"), ("benchmark_symbol", "Benchmark"),
            ("strategy_template", "Template"), ("validation_status", "验证状态"),
            ("classification_source", "分类来源"),
        ):
            print("%s：%s" % (label, result.get(key) or "-"))
        return 0
    except Exception as exc:
        print("添加失败：%s" % exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
