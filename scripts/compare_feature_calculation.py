#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.calculator import FeatureCalculator
from app.features.repository import FeatureRepository
from app.database.session import get_session_factory


def main() -> int:
    parser = argparse.ArgumentParser(description="比较全量与截断计算共同时间点结果")
    parser.add_argument("--symbol", default="US.QQQ")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--feature", default="ema_20")
    args = parser.parse_args()
    db = get_session_factory()()
    try:
        bars = FeatureRepository(db).load_bars(args.symbol, args.interval)
        if len(bars) < 260:
            print("数据不足，无法进行独立比较。")
            return 1
        calculator = FeatureCalculator()
        full = calculator.calculate(bars, args.interval)[args.feature]
        cutoff = max(1, len(bars) - 50)
        truncated = calculator.calculate(bars.iloc[:cutoff], args.interval)[args.feature]
        difference = abs(float(full.iloc[cutoff - 1]) - float(truncated.iloc[-1]))
        print("全量与截断计算比较：%s，共同时间点最大误差=%s" % (args.feature, difference))
        print("未来K线未影响过去结果。" if difference < 1e-12 else "发现差异，请检查。")
        return 0 if difference < 1e-12 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
