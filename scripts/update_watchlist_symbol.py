#!/usr/bin/env python3
import argparse

from app.database.session import get_session_factory
from app.strategy.watchlist import WatchlistService


def main() -> int:
    parser = argparse.ArgumentParser(description="人工更新观察Ticker")
    parser.add_argument("symbol")
    parser.add_argument("--role")
    parser.add_argument("--benchmark")
    parser.add_argument("--template")
    parser.add_argument("--sector")
    parser.add_argument("--notes")
    state = parser.add_mutually_exclusive_group()
    state.add_argument("--enable", action="store_true")
    state.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    changes = {}
    for source, target in (
        ("role", "role"), ("benchmark", "benchmark_symbol"),
        ("template", "strategy_template"), ("sector", "sector"), ("notes", "notes"),
    ):
        value = getattr(args, source)
        if value is not None:
            changes[target] = value
    if args.enable or args.disable:
        changes["enabled"] = args.enable
    if not changes:
        print("未提供任何修改。")
        return 2
    try:
        with get_session_factory()() as db:
            item = WatchlistService(db).update_symbol(args.symbol, **changes)
            print("更新完成：%s，分类来源=%s" % (item.symbol, item.classification_source))
        return 0
    except Exception as exc:
        print("更新失败：%s" % exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
