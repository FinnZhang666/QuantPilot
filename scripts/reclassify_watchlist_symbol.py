#!/usr/bin/env python3
import argparse

from app.database.session import get_session_factory
from app.strategy.watchlist import WatchlistService


def main() -> int:
    parser = argparse.ArgumentParser(description="重新自动分类Ticker")
    parser.add_argument("symbol")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    try:
        with get_session_factory()() as db:
            result = WatchlistService(db).reclassify_symbol(args.symbol, args.confirm)
        if not args.confirm:
            print("预览：该操作会覆盖人工分类字段；添加--confirm才会实际修改。")
        print(result)
        return 0
    except Exception as exc:
        print("重新分类失败：%s" % exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
