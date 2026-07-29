import argparse

from app.database.models import BacktestRun
from app.database.session import get_session_factory


def main():
    parser = argparse.ArgumentParser(description="查看回测结果")
    parser.add_argument("run_id", type=int)
    args = parser.parse_args()
    with get_session_factory()() as db:
        row = db.get(BacktestRun, args.run_id)
        if not row:
            print("回测任务不存在。")
            return 1
        print("回测结果")
        print("标的/周期：%s / %s" % (row.symbol, row.timeframe))
        print("状态：%s" % row.status)
        print("总收益率：%s" % row.total_return_pct)
        print("最大回撤：%s" % row.max_drawdown_pct)
        print("完成交易：%s" % row.closed_trades_count)
        print("Benchmark：%s（%s）" % (row.benchmark_symbol, row.benchmark_status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
