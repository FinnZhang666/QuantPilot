from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_read
from app.database.models import (
    CandidateSignal, FeatureValueRecord, HistoryDataIssue, HistorySyncJob,
    MarketBar, Notification, Opportunity, RuntimeStatus, StrategyRun,
    SystemEvent, WatchlistItem,
    MarketRegime, CandidatePoolEntry,
    OpportunityReview, ReviewStatistic,
)
from app.database.session import get_db, get_engine

router = APIRouter(
    prefix="/api/dashboard", tags=["公司工作台"],
    dependencies=[Depends(require_read)],
)


def _today():
    return datetime.now(timezone.utc).date().isoformat()


@router.get("/summary")
def dashboard_summary(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
):
    day = _today()
    opportunities = dict(db.execute(select(
        Opportunity.status, func.count(),
    ).where(func.date(Opportunity.detected_at) == day).group_by(Opportunity.status)).all())
    directions = dict(db.execute(select(
        Opportunity.direction, func.count(),
    ).where(func.date(Opportunity.detected_at) == day).group_by(Opportunity.direction)).all())
    services = list(db.scalars(select(RuntimeStatus).order_by(RuntimeStatus.service_name)))
    latest = list(db.scalars(select(Opportunity).order_by(
        Opportunity.detected_at.desc(),
    ).limit(10)))
    database_path = settings.database_url.removeprefix("sqlite:///")
    database_size = Path(database_path).stat().st_size if Path(database_path).exists() else 0
    strategy_today = db.scalar(select(func.sum(StrategyRun.bars_evaluated)).where(
        func.date(StrategyRun.started_at) == day,
    )) or 0
    errors_today = db.scalar(select(func.count()).select_from(SystemEvent).where(
        func.date(SystemEvent.created_at) == day, SystemEvent.level == "ERROR",
    )) or 0
    reviews_today = db.scalar(select(func.count()).select_from(OpportunityReview).where(
        func.date(OpportunityReview.review_time) == day,
        OpportunityReview.review_status == "REVIEWED",
    )) or 0
    review_summary = db.scalar(select(ReviewStatistic).where(
        ReviewStatistic.strategy_name == "*", ReviewStatistic.timeframe == "*",
        ReviewStatistic.symbol == "*",
    ))
    review_pending = db.scalar(select(func.count()).select_from(Opportunity).where(
        Opportunity.status.in_(["ACTIVE", "EXPIRED", "REVIEW_PENDING"]),
    )) or 0
    return {
        "services": [_service(row) for row in services],
        "database": {
            "size_bytes": database_size,
            "size_text": _size(database_size),
            "table_count": len(inspect(get_engine()).get_table_names()),
            "core_counts": {
                "market_bars": db.scalar(select(func.count()).select_from(MarketBar)) or 0,
                "feature_values": db.scalar(select(func.max(FeatureValueRecord.id))) or 0,
                "signals": db.scalar(select(func.count()).select_from(CandidateSignal)) or 0,
                "opportunities": db.scalar(select(func.count()).select_from(Opportunity)) or 0,
            },
            "estimated_counts": ["feature_values"],
        },
        "today": {
            "opportunities": sum(opportunities.values()), "long": directions.get("LONG", 0),
            "short": directions.get("SHORT", 0), "status_counts": opportunities,
            "bars_processed": int(strategy_today), "errors": errors_today,
            "reviews_completed": reviews_today,
        },
        "latest_opportunities": [_opportunity(row) for row in latest],
        "recent_errors": [
            _service(row) for row in services if row.last_error_at or row.last_error_message
        ],
        "market_regime": _regime_summary(db.scalar(select(MarketRegime).order_by(
            MarketRegime.bar_time.desc(),
        ).limit(1))),
        "candidate_pool": _candidate_summary(db, day),
        "review": {
            "pending": review_pending,
            "success_rate": str(review_summary.success_rate) if review_summary else "0",
            "average_return": str(review_summary.average_return) if review_summary else "0",
            "average_mfe": str(review_summary.average_mfe) if review_summary else "0",
            "average_mae": str(review_summary.average_mae) if review_summary else "0",
        },
    }


@router.get("/strategy-summary")
def strategy_summary(db: Session = Depends(get_db)):
    rows = db.execute(select(
        CandidateSignal.strategy_name, CandidateSignal.strategy_version,
        CandidateSignal.signal_type, func.count(), func.avg(CandidateSignal.score),
        func.max(CandidateSignal.updated_at),
    ).group_by(
        CandidateSignal.strategy_name, CandidateSignal.strategy_version,
        CandidateSignal.signal_type,
    )).all()
    grouped: Dict[str, dict] = {}
    for name, version, signal_type, count, average, latest in rows:
        target = grouped.setdefault(name, {
            "strategy_name": name, "strategy_version": version,
            "signal_counts": {}, "signal_total": 0, "average_score": 0,
            "latest_run_at": latest, "opportunity_count": 0, "failed_gates": {},
            "supported_timeframes": [],
            "symbol_templates": [], "score_distribution": {},
        })
        target["signal_counts"][signal_type] = count
        target["signal_total"] += count
        target["average_score"] = round(float(average or 0), 2)
        target["latest_run_at"] = max(filter(None, [target["latest_run_at"], latest]), default=None)
    for target in grouped.values():
        target["opportunity_count"] = db.scalar(select(func.count()).select_from(Opportunity).where(
            Opportunity.strategy_name == target["strategy_name"],
        )) or 0
        target["supported_timeframes"] = list(db.scalars(select(
            CandidateSignal.timeframe,
        ).where(CandidateSignal.strategy_name == target["strategy_name"]).distinct()))
        target["symbol_templates"] = list(db.scalars(select(
            WatchlistItem.strategy_template,
        ).where(WatchlistItem.enabled.is_(True)).distinct()))
        scores = list(db.scalars(select(CandidateSignal.score).where(
            CandidateSignal.strategy_name == target["strategy_name"],
        )))
        target["score_distribution"] = {
            "0-39": sum(value < 40 for value in scores),
            "40-59": sum(40 <= value < 60 for value in scores),
            "60-79": sum(60 <= value < 80 for value in scores),
            "80-100": sum(value >= 80 for value in scores),
        }
        risks = db.scalars(select(CandidateSignal.risks_json).where(
            CandidateSignal.strategy_name == target["strategy_name"],
        ).order_by(CandidateSignal.bar_timestamp.desc()).limit(100))
        failed = {}
        for values in risks:
            for value in values or []:
                failed[value] = failed.get(value, 0) + 1
        target["failed_gates"] = dict(sorted(failed.items(), key=lambda item: -item[1])[:10])
    return {"items": list(grouped.values()), "total": len(grouped)}


@router.get("/data-quality")
def data_quality(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    watchlist = list(db.scalars(select(WatchlistItem).order_by(WatchlistItem.symbol)))
    requested = {"US." + item.symbol for item in watchlist}
    bar_rows = db.execute(select(
        MarketBar.symbol, MarketBar.interval, func.count(),
        func.min(MarketBar.timestamp_utc), func.max(MarketBar.timestamp_utc),
    ).where(MarketBar.symbol.in_(requested)).group_by(
        MarketBar.symbol, MarketBar.interval,
    )).all() if requested else []
    bars_by_symbol = {}
    for symbol, interval, count, earliest, latest in bar_rows:
        bars_by_symbol.setdefault(symbol, []).append((interval, count, earliest, latest))
    issues_by_symbol = dict(db.execute(select(
        HistoryDataIssue.symbol, func.count(),
    ).where(HistoryDataIssue.symbol.in_(requested)).group_by(
        HistoryDataIssue.symbol,
    )).all()) if requested else {}
    latest_signals = {}
    signal_rows = db.scalars(select(CandidateSignal).order_by(
        CandidateSignal.symbol, CandidateSignal.bar_timestamp.desc(),
    )).all()
    for row in signal_rows:
        latest_signals.setdefault(row.symbol, row)
    items = []
    for item in watchlist:
        full = "US." + item.symbol
        bars = bars_by_symbol.get(full, [])
        issue_count = issues_by_symbol.get(full, 0)
        feature_count = db.scalar(select(FeatureValueRecord.id).where(
            FeatureValueRecord.symbol == full,
            FeatureValueRecord.quality_status == "VALID",
        ).limit(1))
        latest_signal = latest_signals.get(item.symbol)
        items.append({
            "symbol": item.symbol,
            "timeframes": [
                {"timeframe": interval, "count": count, "earliest": earliest, "latest": latest}
                for interval, count, earliest, latest in bars
            ],
            "bar_count": sum(row[1] for row in bars), "gap_or_issue_count": issue_count,
            "duplicate_count": 0, "feature_calculable": feature_count is not None,
            "strategy_data_status": latest_signal.status if latest_signal else "NO_SIGNAL",
            "latest_data_at": max((row[3] for row in bars if row[3]), default=None),
        })
    database_path = settings.database_url.removeprefix("sqlite:///")
    size = Path(database_path).stat().st_size if Path(database_path).exists() else 0
    table_counts = {
        "market_bars": db.scalar(select(func.count()).select_from(MarketBar)) or 0,
        "feature_values": db.scalar(select(func.max(FeatureValueRecord.id))) or 0,
        "candidate_signals": db.scalar(select(func.count()).select_from(CandidateSignal)) or 0,
        "opportunities": db.scalar(select(func.count()).select_from(Opportunity)) or 0,
    }
    latest_job = db.scalar(select(HistorySyncJob).order_by(HistorySyncJob.created_at.desc()).limit(1))
    return {
        "items": items, "database_size_bytes": size, "database_size_text": _size(size),
        "largest_core_table": max(table_counts, key=table_counts.get) if table_counts else None,
        "core_table_counts": table_counts,
        "estimated_counts": ["feature_values"],
        "latest_import_at": latest_job.finished_at if latest_job else None,
        "latest_import_error": latest_job.error_message if latest_job else None,
    }


def _service(row):
    return {
        "service_name": row.service_name, "status": row.status,
        "last_heartbeat_at": row.last_heartbeat_at, "last_success_at": row.last_success_at,
        "last_error_at": row.last_error_at, "last_error_message": row.last_error_message,
        "metadata": row.metadata_json,
    }


def _regime_summary(row):
    if row is None:
        return {"regime": "UNKNOWN", "confidence": 0, "long_bias": 50, "short_bias": 50}
    return {
        "id": row.id, "regime": row.regime, "confidence": row.confidence,
        "long_bias": row.long_bias, "short_bias": row.short_bias,
        "bar_time": row.bar_time,
    }


def _candidate_summary(db, day):
    counts = dict(db.execute(select(
        CandidatePoolEntry.direction, func.count(),
    ).where(
        CandidatePoolEntry.pool_date == day,
        CandidatePoolEntry.status != "EXPIRED",
    ).group_by(CandidatePoolEntry.direction)).all())
    rows = db.scalars(select(CandidatePoolEntry).where(
        CandidatePoolEntry.pool_date == day,
        CandidatePoolEntry.status != "EXPIRED",
    ).order_by(CandidatePoolEntry.rank, CandidatePoolEntry.symbol).limit(5)).all()
    return {
        "total": sum(counts.values()), "long": counts.get("LONG", 0),
        "short": counts.get("SHORT", 0), "both": counts.get("BOTH", 0),
        "top": [{
            "id": row.id, "rank": row.rank, "symbol": row.symbol,
            "direction": row.direction, "long_score": row.long_score,
            "short_score": row.short_score, "final_score": row.final_score,
            "status": row.status,
        } for row in rows],
    }


def _opportunity(row):
    return {
        "id": row.id, "symbol": row.symbol, "timeframe": row.timeframe,
        "direction": row.direction, "strategy_name": row.strategy_name,
        "score": row.score, "confidence": row.confidence, "status": row.status,
        "detected_at": row.detected_at, "notification_status": row.notification_status,
    }


def _size(value):
    if value >= 1024 ** 3:
        return "%.2f GB" % (value / 1024 ** 3)
    if value >= 1024 ** 2:
        return "%.1f MB" % (value / 1024 ** 2)
    return "%.1f KB" % (value / 1024)
