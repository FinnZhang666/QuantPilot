#!/usr/bin/env python3
from app.database.session import get_session_factory
from app.strategy.watchlist import WatchlistService


def main() -> int:
    with get_session_factory()() as db:
        stats = WatchlistService(db).initialize_defaults()
    print("默认观察池初始化完成")
    print("新增：%s" % stats["added"])
    print("已存在：%s" % stats["existing"])
    print("重新启用：%s" % stats["reactivated"])
    print("待验证：%s" % stats["pending_validation"])
    print("失败：%s" % stats["failed"])
    return 0 if stats["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
