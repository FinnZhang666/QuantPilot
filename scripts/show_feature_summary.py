#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.database.models import FeatureValueRecord
from app.database.session import get_session_factory


def main() -> int:
    db = get_session_factory()()
    try:
        print("特征数据摘要")
        rows = db.execute(select(FeatureValueRecord.symbol, FeatureValueRecord.interval, func.count(), func.min(FeatureValueRecord.timestamp_utc), func.max(FeatureValueRecord.timestamp_utc)).group_by(FeatureValueRecord.symbol, FeatureValueRecord.interval).order_by(FeatureValueRecord.symbol, FeatureValueRecord.interval))
        for symbol, interval, count, earliest, latest in rows:
            print("%s %s：%s条，%s 至 %s" % (symbol, interval, count, earliest, latest))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

