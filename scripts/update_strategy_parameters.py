#!/usr/bin/env python3
import argparse

from app.database.session import get_session_factory
from app.strategy.watchlist import WatchlistService


def parse_updates(values):
    result = {}
    for value in values:
        if "=" not in value:
            raise ValueError("参数必须使用name=value格式")
        key, raw = value.split("=", 1)
        result[key] = raw
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="修改策略参数")
    parser.add_argument("symbol")
    parser.add_argument("--strategy", default="pullback_restrength")
    parser.add_argument("--set", action="append", default=[])
    args = parser.parse_args()
    if args.strategy != "pullback_restrength":
        print("当前只支持pullback_restrength策略。")
        return 2
    try:
        with get_session_factory()() as db:
            result = WatchlistService(db).update_parameters(
                args.symbol, parse_updates(args.set),
            )
        print("参数修改完成（默认参数，尚未经过历史回测优化）")
        for key in sorted(result["after"]):
            if result["before"].get(key) != result["after"].get(key):
                print("- %s：%s → %s" % (key, result["before"].get(key), result["after"].get(key)))
        print("Parameters Hash：%s" % result["parameters_hash"])
        return 0
    except Exception as exc:
        print("参数修改失败：%s" % exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
