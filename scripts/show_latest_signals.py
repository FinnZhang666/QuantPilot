#!/usr/bin/env python3
import argparse

from sqlalchemy import desc, select

from app.database.models import CandidateSignal
from app.database.session import get_session_factory


def main() -> int:
    parser = argparse.ArgumentParser(description="查看最新候选信号")
    parser.add_argument("--symbol")
    parser.add_argument("--timeframe")
    parser.add_argument("--signal-type")
    parser.add_argument("--min-score", type=int, default=0)
    parser.add_argument("--min-confidence", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    query = select(CandidateSignal).where(
        CandidateSignal.score >= args.min_score,
        CandidateSignal.confidence >= args.min_confidence,
    )
    if args.symbol:
        query = query.where(CandidateSignal.symbol == args.symbol.upper().replace("US.", ""))
    if args.timeframe:
        query = query.where(CandidateSignal.timeframe == args.timeframe)
    if args.signal_type:
        query = query.where(CandidateSignal.signal_type == args.signal_type)
    with get_session_factory()() as db:
        rows = db.scalars(query.order_by(desc(CandidateSignal.bar_timestamp)).limit(min(args.limit, 1000)))
        print("Ticker\t周期\t时间\tSignal\tScore\tConfidence\tSummary")
        for row in rows:
            print("%s\t%s\t%s\t%s\t%s\t%s\t%s" % (
                row.symbol, row.timeframe, row.bar_timestamp, row.signal_type,
                row.score, row.confidence, row.summary_zh,
            ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
