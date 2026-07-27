import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import (
    CandidateSignal, MarketBar, RealtimeBar, StrategyParameterSet, StrategyRun,
    WatchlistItem, WatchlistTimeframe,
)
from app.strategy.constants import (
    ROLES, SIGNAL_STATUSES, SIGNAL_TYPES, SYMBOL_PATTERN, TEMPLATES,
)
from app.strategy.templates import parameters_hash


class StrategyQualityService:
    def inspect(self, db: Session) -> Dict[str, object]:
        issues: List[dict] = []
        items = list(db.scalars(select(WatchlistItem)))
        item_symbols = {item.symbol for item in items}
        for item in items:
            if not SYMBOL_PATTERN.fullmatch(item.symbol):
                issues.append({"type": "INVALID_SYMBOL", "symbol": item.symbol})
            if item.role not in ROLES:
                issues.append({"type": "INVALID_ROLE", "symbol": item.symbol})
            if item.strategy_template not in TEMPLATES:
                issues.append({"type": "INVALID_TEMPLATE", "symbol": item.symbol})
            if item.benchmark_symbol == item.symbol:
                issues.append({"type": "SELF_BENCHMARK", "symbol": item.symbol})
            if item.role == "TRADING" and not item.benchmark_symbol:
                issues.append({"type": "MISSING_BENCHMARK", "symbol": item.symbol})
            if item.benchmark_symbol and item.benchmark_symbol not in item_symbols:
                issues.append({"type": "BENCHMARK_NOT_WATCHED", "symbol": item.symbol})
        for row in db.scalars(select(StrategyParameterSet)):
            if not isinstance(row.parameters_json, dict):
                issues.append({"type": "INVALID_PARAMETER_JSON", "id": row.id})
            elif parameters_hash(row.parameters_json) != row.parameters_hash:
                issues.append({"type": "PARAMETER_HASH_MISMATCH", "id": row.id})
        enabled_parameter_conflicts = db.execute(select(
            StrategyParameterSet.watchlist_item_id, StrategyParameterSet.strategy_name,
            StrategyParameterSet.strategy_version, func.count(),
        ).where(StrategyParameterSet.enabled.is_(True)).group_by(
            StrategyParameterSet.watchlist_item_id, StrategyParameterSet.strategy_name,
            StrategyParameterSet.strategy_version,
        ).having(func.count() > 1)).all()
        for item_id, name, version, count in enabled_parameter_conflicts:
            issues.append({"type": "MULTIPLE_ENABLED_PARAMETERS", "watchlist_item_id": item_id})
        now = datetime.now(timezone.utc)
        for signal in db.scalars(select(CandidateSignal)):
            timestamp = signal.bar_timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if timestamp > now:
                issues.append({"type": "FUTURE_SIGNAL", "id": signal.id})
            if signal.signal_type not in SIGNAL_TYPES:
                issues.append({"type": "INVALID_SIGNAL_TYPE", "id": signal.id})
            if signal.status not in SIGNAL_STATUSES:
                issues.append({"type": "INVALID_SIGNAL_STATUS", "id": signal.id})
            if not 0 <= signal.score <= 100:
                issues.append({"type": "SCORE_OUT_OF_RANGE", "id": signal.id})
            if not 0 <= signal.confidence <= 100:
                issues.append({"type": "CONFIDENCE_OUT_OF_RANGE", "id": signal.id})
            for field, expected in (
                ("reasons_json", list), ("risks_json", list),
                ("components_json", dict), ("feature_refs_json", dict),
            ):
                if not isinstance(getattr(signal, field), expected):
                    issues.append({"type": "INVALID_" + field.upper(), "id": signal.id})
            bar_exists = db.scalar(select(MarketBar.id).where(
                MarketBar.symbol == "US." + signal.symbol,
                MarketBar.interval == signal.timeframe,
                MarketBar.timestamp_utc == signal.bar_timestamp,
            ).limit(1))
            if not bar_exists:
                bar_exists = db.scalar(select(RealtimeBar.id).where(
                    RealtimeBar.symbol == "US." + signal.symbol,
                    RealtimeBar.interval == signal.timeframe,
                    RealtimeBar.timestamp_utc == signal.bar_timestamp,
                    RealtimeBar.is_closed.is_(True),
                ).limit(1))
            if not bar_exists:
                issues.append({"type": "SIGNAL_WITHOUT_CLOSED_BAR", "id": signal.id})
        duplicate_signals = db.execute(select(
            CandidateSignal.symbol, CandidateSignal.timeframe,
            CandidateSignal.bar_timestamp, CandidateSignal.strategy_name,
            CandidateSignal.strategy_version, CandidateSignal.parameters_hash,
            func.count(),
        ).group_by(
            CandidateSignal.symbol, CandidateSignal.timeframe,
            CandidateSignal.bar_timestamp, CandidateSignal.strategy_name,
            CandidateSignal.strategy_version, CandidateSignal.parameters_hash,
        ).having(func.count() > 1)).all()
        for row in duplicate_signals:
            issues.append({"type": "DUPLICATE_SIGNAL", "symbol": row[0]})
        for item in items:
            if not item.enabled or item.role != "TRADING":
                continue
            for timeframe in db.scalars(select(WatchlistTimeframe.timeframe).where(
                WatchlistTimeframe.watchlist_item_id == item.id,
                WatchlistTimeframe.enabled.is_(True),
            )):
                latest_bar = db.scalar(select(func.max(MarketBar.timestamp_utc)).where(
                    MarketBar.symbol == "US." + item.symbol,
                    MarketBar.interval == timeframe,
                ))
                latest_signal = db.scalar(select(func.max(CandidateSignal.bar_timestamp)).where(
                    CandidateSignal.symbol == item.symbol,
                    CandidateSignal.timeframe == timeframe,
                ))
                if latest_bar is None:
                    issues.append({"type": "NO_BAR_DATA", "symbol": item.symbol, "timeframe": timeframe})
                elif latest_signal is None or latest_signal < latest_bar:
                    issues.append({"type": "SIGNAL_STALE", "symbol": item.symbol, "timeframe": timeframe})
        stale_runs = db.scalar(select(func.count()).select_from(StrategyRun).where(
            StrategyRun.status == "RUNNING",
            StrategyRun.started_at < now - timedelta(hours=1),
        )) or 0
        signal_type_counts = dict(db.execute(select(
            CandidateSignal.signal_type, func.count(),
        ).group_by(CandidateSignal.signal_type)).all())
        signal_status_counts = dict(db.execute(select(
            CandidateSignal.status, func.count(),
        ).group_by(CandidateSignal.status)).all())
        return {
            "watchlist_total": len(items),
            "enabled_total": sum(1 for item in items if item.enabled),
            "trading_total": sum(1 for item in items if item.role == "TRADING"),
            "benchmark_total": sum(1 for item in items if item.role.endswith("BENCHMARK")),
            "risk_indicator_total": sum(1 for item in items if item.role == "RISK_INDICATOR"),
            "valid_total": sum(1 for item in items if item.validation_status == "VALID"),
            "pending_total": sum(1 for item in items if item.validation_status == "PENDING_VALIDATION"),
            "signal_total": db.scalar(select(func.count()).select_from(CandidateSignal)) or 0,
            "signal_type_counts": signal_type_counts,
            "missing_feature_total": signal_status_counts.get("MISSING_FEATURE", 0),
            "warmup_total": signal_status_counts.get("WARMUP", 0),
            "error_total": signal_status_counts.get("ERROR", 0),
            "duplicate_signal_total": len(duplicate_signals),
            "future_signal_total": sum(1 for issue in issues if issue["type"] == "FUTURE_SIGNAL"),
            "unclosed_bar_signal_total": sum(1 for issue in issues if issue["type"] == "SIGNAL_WITHOUT_CLOSED_BAR"),
            "parameter_hash_error_total": sum(1 for issue in issues if issue["type"] == "PARAMETER_HASH_MISMATCH"),
            "stale_running_total": stale_runs,
            "issues": issues,
        }
