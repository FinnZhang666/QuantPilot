#!/usr/bin/env python3
import argparse
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.enums import AdjustmentType, BarInterval
from app.database.models import Instrument
from app.database.session import get_session_factory
from app.historical.factory import build_history_provider
from app.historical.sync_service import HistoricalDataSyncService, STATUS_TEXT


def parse_date(value: str, end: bool = False) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return parsed + timedelta(days=1) - timedelta(microseconds=1) if end else parsed


def default_start(interval: BarInterval, settings, end: datetime) -> datetime:
    days: Dict[BarInterval, int] = {
        BarInterval.DAY_1: settings.history_daily_years * 365,
        BarInterval.HOUR_1: settings.history_60m_years * 365,
        BarInterval.MIN_30: settings.history_15m_days,
        BarInterval.MIN_15: settings.history_15m_days,
        BarInterval.MIN_5: settings.history_5m_days,
        BarInterval.MIN_1: settings.history_1m_days,
    }
    return end - timedelta(days=days[interval])


def main() -> int:
    parser = argparse.ArgumentParser(description="同步Moomoo历史行情")
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--intervals", nargs="+", choices=[item.value for item in BarInterval])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    if not args.all and (not args.symbols or not args.intervals):
        parser.error("必须指定--symbols和--intervals，或使用--all。")
    settings = get_settings()
    configure_logging(settings.log_level)
    adjustment = AdjustmentType(settings.history_adjustment_type)
    end = parse_date(args.end, True) if args.end else datetime.now(timezone.utc)
    with get_session_factory()() as db:
        if args.all:
            symbols = list(db.scalars(select(Instrument.symbol).where(Instrument.is_supported.is_(True))))
            intervals = list(BarInterval)
        else:
            symbols = [value.upper() for value in args.symbols]
            intervals = [BarInterval(value) for value in args.intervals]
        service = HistoricalDataSyncService(db, build_history_provider(settings))
        exit_code = 0
        for symbol in symbols:
            for interval in intervals:
                start = parse_date(args.start) if args.start else default_start(interval, settings, end)
                job = service.sync_symbol(
                    symbol, interval, start, end, adjustment, args.incremental, args.repair
                )
                duration = (
                    (job.finished_at - job.started_at).total_seconds()
                    if job.started_at and job.finished_at else 0
                )
                print(
                    f"{symbol} {interval.value}：{STATUS_TEXT.get(job.status, job.status)}；"
                    f"接收{job.rows_received}，插入{job.rows_inserted}，更新{job.rows_updated}，"
                    f"跳过{job.rows_skipped}，分页{job.pages_requested}，耗时{duration:.2f}秒"
                )
                if job.error_message:
                    print(f"  错误：{job.error_code} - {job.error_message}")
                if job.status == "FAILED":
                    exit_code = 2
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
