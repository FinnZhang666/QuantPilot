from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.models import (
    FeatureValueRecord, MarketBar, Opportunity, OpportunityReview, ReviewStatistic,
)
from app.review.config import load_review_windows
from app.review.engine import OpportunityReviewEngine


class OpportunityReviewService:
    PENDING_STATUSES = ("ACTIVE", "EXPIRED", "REVIEW_PENDING")

    def __init__(self, db: Session, settings: Optional[Settings] = None):
        self.db = db
        self.settings = settings or get_settings()
        config = load_review_windows(self.settings.opportunity_review_windows_file)
        self.config_version = config["version"]
        self.windows = config["windows"]
        self.max_window_name = max(self.windows, key=lambda key: self.windows[key])
        self.max_window = self.windows[self.max_window_name]
        self.engine = OpportunityReviewEngine()

    def pending(self, limit: int = 100, symbol: Optional[str] = None) -> List[Opportunity]:
        query = select(Opportunity).outerjoin(
            OpportunityReview, OpportunityReview.opportunity_id == Opportunity.id,
        ).where(
            Opportunity.status.in_(self.PENDING_STATUSES),
            OpportunityReview.id.is_(None),
        )
        if symbol:
            query = query.where(Opportunity.symbol == _symbol(symbol))
        return list(self.db.scalars(query.order_by(Opportunity.bar_time).limit(limit)))

    def run(self, limit: Optional[int] = None, symbol: Optional[str] = None) -> Dict[str, object]:
        batch_size = limit or self.settings.opportunity_review_batch_size
        result = {"scanned": 0, "reviewed": 0, "pending": 0, "failed": 0, "ids": []}
        for opportunity in self.pending(batch_size, symbol):
            result["scanned"] += 1
            try:
                outcome = self.review_opportunity(opportunity)
                result[outcome] += 1
                if outcome in {"reviewed", "failed"}:
                    review = self.db.scalar(select(OpportunityReview).where(
                        OpportunityReview.opportunity_id == opportunity.id,
                    ))
                    if review:
                        result["ids"].append(review.id)
            except Exception as exc:
                self.db.rollback()
                self._save_failure(opportunity.id, type(exc).__name__ + "：" + str(exc))
                result["failed"] += 1
        self.refresh_statistics()
        return result

    def review_opportunity(self, opportunity: Opportunity) -> str:
        existing = self.db.scalar(select(OpportunityReview).where(
            OpportunityReview.opportunity_id == opportunity.id,
        ))
        if existing is not None:
            return "reviewed" if existing.review_status == "REVIEWED" else "failed"
        start = _aware(opportunity.bar_time)
        horizon = start + self.max_window
        latest = self.db.scalar(select(func.max(MarketBar.timestamp_utc)).where(
            MarketBar.symbol == "US." + opportunity.symbol,
            MarketBar.interval == opportunity.timeframe,
        ))
        if latest is None:
            return self._save_failure(opportunity.id, "缺少历史K线，无法完成复盘。")
        if _aware(latest) < horizon:
            opportunity.status = "REVIEW_PENDING"
            self.db.commit()
            return "pending"
        rows = list(self.db.scalars(select(MarketBar).where(
            MarketBar.symbol == "US." + opportunity.symbol,
            MarketBar.interval == opportunity.timeframe,
            MarketBar.timestamp_utc > start,
            MarketBar.timestamp_utc <= horizon,
        ).order_by(MarketBar.timestamp_utc)))
        if not rows:
            return self._save_failure(opportunity.id, "复盘窗口内没有可用K线。")
        path = [{
            "timestamp": _aware(row.timestamp_utc),
            "open": str(row.open), "high": str(row.high), "low": str(row.low),
            "close": str(row.close), "volume": row.volume,
        } for row in rows]
        atr = self._atr(opportunity)
        outcome = self.engine.evaluate(
            opportunity, path, self.windows, self.config_version, atr,
        )
        metrics = outcome["metrics"]
        review = OpportunityReview(
            opportunity_id=opportunity.id, review_status="REVIEWED",
            review_time=datetime.now(timezone.utc),
            holding_bars=metrics["holding_bars"],
            holding_minutes=metrics["holding_minutes"],
            holding_days=metrics["holding_days"],
            entry_reference_price=opportunity.entry_reference_price,
            exit_reference_price=metrics["exit_price"], last_price=metrics["last_price"],
            mfe_percent=metrics["mfe_percent"], mae_percent=metrics["mae_percent"],
            return_percent=metrics["return_percent"],
            max_close_return=metrics["max_close_return"],
            min_close_return=metrics["min_close_return"],
            target_hit=metrics["target_hit"], stop_hit=metrics["stop_hit"],
            expired=bool(opportunity.expiry_at and _aware(opportunity.expiry_at) <= datetime.now(timezone.utc)),
            review_window=self.max_window_name,
            price_path_json=[dict(item, timestamp=item["timestamp"].isoformat()) for item in path],
            statistics_json=outcome["statistics"],
            reason_json={"status": "COMPLETED", "message": "复盘窗口已完成。"},
        )
        self.db.add(review)
        opportunity.status = "REVIEWED"
        self.db.commit()
        return "reviewed"

    def get(self, review_id: int) -> Optional[OpportunityReview]:
        return self.db.get(OpportunityReview, review_id)

    def recent(self, limit: int = 10, symbol: Optional[str] = None):
        query = select(OpportunityReview, Opportunity).join(
            Opportunity, Opportunity.id == OpportunityReview.opportunity_id,
        )
        if symbol:
            query = query.where(Opportunity.symbol == _symbol(symbol))
        return list(self.db.execute(query.order_by(desc(OpportunityReview.review_time)).limit(limit)))

    def refresh_statistics(self) -> None:
        groups = list(self.db.execute(select(
            Opportunity.strategy_name, Opportunity.strategy_version,
            Opportunity.timeframe, Opportunity.symbol,
        ).join(OpportunityReview).distinct()))
        keys = set()
        for strategy, version, timeframe, symbol in groups:
            keys.update({
                (strategy, version, timeframe, symbol),
                (strategy, version, "*", "*"), ("*", "*", timeframe, "*"),
                ("*", "*", "*", symbol), ("*", "*", "*", "*"),
            })
        for key in keys:
            self._refresh_group(*key)
        self.db.commit()

    def _refresh_group(self, strategy: str, version: str, timeframe: str, symbol: str):
        filters = []
        if strategy != "*":
            filters.extend([Opportunity.strategy_name == strategy, Opportunity.strategy_version == version])
        if timeframe != "*":
            filters.append(Opportunity.timeframe == timeframe)
        if symbol != "*":
            filters.append(Opportunity.symbol == symbol)
        rows = list(self.db.execute(select(OpportunityReview, Opportunity).join(
            Opportunity, Opportunity.id == OpportunityReview.opportunity_id,
        ).where(*filters)))
        complete = [row for row, _ in rows if row.review_status == "REVIEWED"]
        total_opportunities = self.db.scalar(select(func.count()).select_from(Opportunity).where(*filters)) or 0
        values = [Decimal(str(row.return_percent)) for row in complete if row.return_percent is not None]
        mfes = [Decimal(str(row.mfe_percent)) for row in complete if row.mfe_percent is not None]
        maes = [Decimal(str(row.mae_percent)) for row in complete if row.mae_percent is not None]
        record = self.db.scalar(select(ReviewStatistic).where(
            ReviewStatistic.strategy_name == strategy,
            ReviewStatistic.strategy_version == version,
            ReviewStatistic.timeframe == timeframe, ReviewStatistic.symbol == symbol,
        )) or ReviewStatistic(
            strategy_name=strategy, strategy_version=version, timeframe=timeframe, symbol=symbol,
        )
        if record.id is None:
            self.db.add(record)
        record.total_reviews = len(complete)
        record.long_count = sum(1 for row, op in rows if row.review_status == "REVIEWED" and op.direction == "LONG")
        record.short_count = sum(1 for row, op in rows if row.review_status == "REVIEWED" and op.direction == "SHORT")
        record.success_rate = _average([Decimal("100") if value > 0 else Decimal("0") for value in values])
        record.average_return = _average(values)
        record.average_mfe = _average(mfes)
        record.average_mae = _average(maes)
        record.maximum_return = max(values) if values else Decimal("0")
        record.maximum_drawdown = min(maes) if maes else Decimal("0")
        record.review_coverage_rate = (
            Decimal(len(rows)) / Decimal(total_opportunities) * Decimal("100")
            if total_opportunities else Decimal("0")
        )
        record.data_insufficient_count = sum(1 for row, _ in rows if row.review_status == "REVIEW_FAILED")

    def _save_failure(self, opportunity_id: int, message: str) -> str:
        opportunity = self.db.get(Opportunity, opportunity_id)
        existing = self.db.scalar(select(OpportunityReview).where(
            OpportunityReview.opportunity_id == opportunity_id,
        ))
        if existing is None:
            self.db.add(OpportunityReview(
                opportunity_id=opportunity_id, review_status="REVIEW_FAILED",
                review_time=datetime.now(timezone.utc), holding_bars=0,
                holding_minutes=0, holding_days=0,
                entry_reference_price=opportunity.entry_reference_price,
                expired=opportunity.status == "EXPIRED",
                review_window=self.max_window_name, price_path_json=[],
                statistics_json={"config_version": self.config_version},
                reason_json={"status": "DATA_INSUFFICIENT", "message": message},
            ))
        opportunity.status = "REVIEW_FAILED"
        self.db.commit()
        return "failed"

    def _atr(self, opportunity):
        row = self.db.scalar(select(FeatureValueRecord).where(
            FeatureValueRecord.symbol == "US." + opportunity.symbol,
            FeatureValueRecord.interval == opportunity.timeframe,
            FeatureValueRecord.feature_name == "atr_14",
            FeatureValueRecord.timestamp_utc <= opportunity.bar_time,
            FeatureValueRecord.quality_status == "VALID",
        ).order_by(desc(FeatureValueRecord.timestamp_utc)).limit(1))
        return Decimal(str(row.value_decimal)) if row and row.value_decimal is not None else None


def _average(values):
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def _symbol(value):
    return value.upper().replace("US.", "")


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
