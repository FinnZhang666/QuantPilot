#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.database.models import FeatureQualityIssue, FeatureValueRecord
from app.database.session import get_session_factory


def main() -> int:
    parser = argparse.ArgumentParser(description="检查特征质量")
    parser.add_argument("--symbols", nargs="+")
    args = parser.parse_args()
    db = get_session_factory()()
    try:
        query = select(FeatureValueRecord.quality_status, func.count()).group_by(FeatureValueRecord.quality_status)
        if args.symbols:
            query = query.where(FeatureValueRecord.symbol.in_([item.upper() for item in args.symbols]))
        print("特征质量检查")
        for status, count in db.execute(query):
            print("- %s：%s" % (status, count))
        issue_query = select(func.count()).select_from(FeatureQualityIssue).where(FeatureQualityIssue.resolved_at.is_(None))
        if args.symbols:
            issue_query = issue_query.where(FeatureQualityIssue.symbol.in_([item.upper() for item in args.symbols]))
        print("- 未解决质量问题：%s" % db.scalar(issue_query))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
