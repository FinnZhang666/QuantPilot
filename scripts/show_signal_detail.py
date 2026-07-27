#!/usr/bin/env python3
import argparse
from datetime import datetime

from sqlalchemy import select

from app.database.models import CandidateSignal
from app.database.session import get_session_factory


def main() -> int:
    parser = argparse.ArgumentParser(description="查看候选信号详情")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--timestamp", required=True)
    args = parser.parse_args()
    timestamp = datetime.fromisoformat(args.timestamp.replace("Z", "+00:00"))
    with get_session_factory()() as db:
        row = db.scalar(select(CandidateSignal).where(
            CandidateSignal.symbol == args.symbol.upper().replace("US.", ""),
            CandidateSignal.timeframe == args.timeframe,
            CandidateSignal.bar_timestamp == timestamp,
        ))
        if not row:
            print("未找到对应Signal。")
            return 2
        print("Summary：%s" % row.summary_zh)
        print("Reasons：%s" % row.reasons_json)
        print("Risks：%s" % row.risks_json)
        print("Components：%s" % row.components_json)
        print("Feature References：%s" % row.feature_refs_json)
        print("Parameters Hash：%s" % row.parameters_hash)
        print("Strategy Version：%s" % row.strategy_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
