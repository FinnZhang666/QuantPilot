#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import BarInterval, FeatureJobType
from app.database.models import Instrument
from app.database.session import get_session_factory
from app.features.pipeline import FeatureCalculationService
from app.features.registry import FeatureRegistry
from app.features.repository import FeatureRepository


def parse_time(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None


def main() -> int:
    parser = argparse.ArgumentParser(description="批量计算版本化量化特征")
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--intervals", nargs="+", choices=[item.value for item in BarInterval])
    parser.add_argument("--features", nargs="+")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--realtime", action="store_true", help="仅使用闭合实时1分钟K线")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not args.all and not args.symbols:
        parser.error("必须指定--symbols或--all")
    settings = get_settings()
    db = get_session_factory()()
    try:
        registry = FeatureRegistry.defaults()
        repo = FeatureRepository(
            db, settings.feature_write_batch_size, settings.feature_read_chunk_size
        )
        repo.initialize_definitions(registry.list())
        symbols = args.symbols
        if args.all:
            symbols = list(db.scalars(select(Instrument.symbol).where(Instrument.is_active.is_(True), Instrument.is_supported.is_(True)).order_by(Instrument.symbol)))
        intervals = [BarInterval(item) for item in (args.intervals or ["1d", "60m", "15m", "5m", "1m"])]
        service = FeatureCalculationService(repo, registry)
        now = datetime.now(timezone.utc)
        for symbol in symbols:
            for interval in intervals:
                start = parse_time(args.start)
                end = parse_time(args.end) or now
                if args.all and start is None:
                    days = {"1d": 365 * settings.history_daily_years, "60m": 365 * settings.history_60m_years, "15m": settings.history_15m_days, "5m": settings.history_5m_days, "1m": settings.history_1m_days}.get(interval.value)
                    start = now - timedelta(days=days) if days else None
                job_type = FeatureJobType.REPAIR if args.repair else FeatureJobType.INCREMENTAL if args.incremental else FeatureJobType.FULL
                job = service.calculate_symbol(symbol.upper(), interval, args.features, start, end, job_type, args.realtime)
                meta = job.metadata_json or {}
                print("%s %s：%s，输入%s，输出%s，失败特征%s，耗时%ss，吞吐%s值/s" % (
                    symbol.upper(), interval.value, job.status, job.input_rows, job.output_rows,
                    job.failed_features, meta.get("duration_seconds", 0), meta.get("rows_per_second", 0),
                ))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
