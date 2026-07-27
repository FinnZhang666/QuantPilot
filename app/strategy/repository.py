import uuid
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database.models import (
    CandidateSignal, FeatureValueRecord, MarketBar, RealtimeBar,
    StrategyParameterSet, StrategyRun, WatchlistItem, WatchlistTimeframe,
)
from app.strategy.constants import STRATEGY_NAME, STRATEGY_VERSION
from app.strategy.models import SignalEvaluation


class StrategyRepository:
    def __init__(self, db: Session, chunk_size: int = 5000):
        self.db = db
        self.chunk_size = chunk_size

    def create_run(self, run_type: str, symbols: List[str], timeframes: List[str], free_disk_gb: float) -> StrategyRun:
        run = StrategyRun(
            run_id=str(uuid.uuid4()), run_type=run_type, strategy_name=STRATEGY_NAME,
            strategy_version=STRATEGY_VERSION, symbols_json=symbols,
            timeframes_json=timeframes, started_at=datetime.now(timezone.utc),
            status="RUNNING", free_disk_gb=free_disk_gb,
        )
        self.db.add(run)
        self.db.commit()
        return run

    def finish_run(self, run: StrategyRun, status: str, began: float, errors: Dict[str, str]) -> StrategyRun:
        import time
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.elapsed_seconds = round(time.monotonic() - began, 6)
        run.error_summary = errors
        self.db.add(run)
        self.db.commit()
        return run

    def get_parameter_set(self, watchlist_item_id: int) -> Optional[StrategyParameterSet]:
        return self.db.scalar(select(StrategyParameterSet).where(
            StrategyParameterSet.watchlist_item_id == watchlist_item_id,
            StrategyParameterSet.strategy_name == STRATEGY_NAME,
            StrategyParameterSet.strategy_version == STRATEGY_VERSION,
            StrategyParameterSet.enabled.is_(True),
        ))

    def bar_timestamps(
        self, symbol: str, timeframe: str, start: Optional[datetime],
        end: Optional[datetime], realtime: bool = False,
    ) -> List[datetime]:
        model = RealtimeBar if realtime else MarketBar
        query = select(model.timestamp_utc).where(
            model.symbol == "US." + symbol, model.interval == timeframe,
        )
        if realtime:
            query = query.where(model.is_closed.is_(True))
        else:
            query = query.where(
                model.adjustment_type == "FORWARD", model.data_source == "MOOMOO",
            )
        if start:
            query = query.where(model.timestamp_utc >= start)
        if end:
            query = query.where(model.timestamp_utc <= end)
        if realtime:
            query = query.order_by(desc(model.timestamp_utc)).limit(1)
            value = self.db.scalar(query)
            return [value] if value else []
        return list(self.db.scalars(query.order_by(model.timestamp_utc)))

    def estimate_bars(self, symbols: Iterable[str], timeframes: Iterable[str], start: Optional[datetime], end: Optional[datetime]) -> int:
        query = select(func.count()).select_from(MarketBar).where(
            MarketBar.symbol.in_(["US." + value for value in symbols]),
            MarketBar.interval.in_(list(timeframes)),
            MarketBar.adjustment_type == "FORWARD",
            MarketBar.data_source == "MOOMOO",
        )
        if start:
            query = query.where(MarketBar.timestamp_utc >= start)
        if end:
            query = query.where(MarketBar.timestamp_utc <= end)
        return int(self.db.scalar(query) or 0)

    def latest_bar_timestamp(self, symbol: str, timeframe: str) -> Optional[datetime]:
        return self.db.scalar(select(func.max(MarketBar.timestamp_utc)).where(
            MarketBar.symbol == "US." + symbol,
            MarketBar.interval == timeframe,
            MarketBar.adjustment_type == "FORWARD",
            MarketBar.data_source == "MOOMOO",
        ))

    def feature_values(
        self, symbol: str, timeframe: str, timestamp: datetime, names: Iterable[str],
        data_source: str = "MOOMOO",
    ) -> Dict[str, FeatureValueRecord]:
        rows = self.db.scalars(select(FeatureValueRecord).where(
            FeatureValueRecord.symbol == "US." + symbol,
            FeatureValueRecord.interval == timeframe,
            FeatureValueRecord.timestamp_utc == timestamp,
            FeatureValueRecord.feature_name.in_(list(names)),
            FeatureValueRecord.feature_version == "1.0.0",
            FeatureValueRecord.data_source == data_source,
        ))
        return {row.feature_name: row for row in rows}

    def previous_feature_value(
        self, symbol: str, timeframe: str, timestamp: datetime, name: str,
        data_source: str = "MOOMOO",
    ) -> Optional[FeatureValueRecord]:
        return self.db.scalar(select(FeatureValueRecord).where(
            FeatureValueRecord.symbol == "US." + symbol,
            FeatureValueRecord.interval == timeframe,
            FeatureValueRecord.timestamp_utc < timestamp,
            FeatureValueRecord.feature_name == name,
            FeatureValueRecord.feature_version == "1.0.0",
            FeatureValueRecord.data_source == data_source,
        ).order_by(desc(FeatureValueRecord.timestamp_utc)).limit(1))

    def latest_signal_timestamp(self, symbol: str, timeframe: str, parameters_hash: str) -> Optional[datetime]:
        return self.db.scalar(select(func.max(CandidateSignal.bar_timestamp)).where(
            CandidateSignal.symbol == symbol, CandidateSignal.timeframe == timeframe,
            CandidateSignal.strategy_name == STRATEGY_NAME,
            CandidateSignal.strategy_version == STRATEGY_VERSION,
            CandidateSignal.parameters_hash == parameters_hash,
        ))

    def upsert_signal(
        self, item: WatchlistItem, timeframe: str, timestamp: datetime,
        parameters_hash: str, evaluation: SignalEvaluation,
    ) -> Tuple[int, int]:
        existing = self.db.scalar(select(CandidateSignal.id).where(
            CandidateSignal.symbol == item.symbol, CandidateSignal.market == item.market,
            CandidateSignal.timeframe == timeframe,
            CandidateSignal.bar_timestamp == timestamp,
            CandidateSignal.strategy_name == STRATEGY_NAME,
            CandidateSignal.strategy_version == STRATEGY_VERSION,
            CandidateSignal.parameters_hash == parameters_hash,
        ))
        statement = sqlite_insert(CandidateSignal).values(
            symbol=item.symbol, market=item.market, timeframe=timeframe,
            bar_timestamp=timestamp, strategy_name=STRATEGY_NAME,
            strategy_version=STRATEGY_VERSION, parameters_hash=parameters_hash,
            signal_type=evaluation.signal_type, score=evaluation.score,
            confidence=evaluation.confidence, status=evaluation.status,
            summary_zh=evaluation.summary_zh, reasons_json=evaluation.reasons,
            risks_json=evaluation.risks, feature_refs_json=evaluation.feature_refs,
            components_json=evaluation.components,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=[
                "symbol", "market", "timeframe", "bar_timestamp", "strategy_name",
                "strategy_version", "parameters_hash",
            ],
            set_={
                "signal_type": evaluation.signal_type, "score": evaluation.score,
                "confidence": evaluation.confidence, "status": evaluation.status,
                "summary_zh": evaluation.summary_zh, "reasons_json": evaluation.reasons,
                "risks_json": evaluation.risks, "feature_refs_json": evaluation.feature_refs,
                "components_json": evaluation.components,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        self.db.execute(statement)
        self.db.commit()
        return (0, 1) if existing else (1, 0)

    def upsert_signals(self, records: List[tuple]) -> int:
        if not records:
            return 0
        now = datetime.now(timezone.utc)
        rows = []
        for item, timeframe, timestamp, param_hash, evaluation in records:
            rows.append({
                "symbol": item.symbol, "market": item.market, "timeframe": timeframe,
                "bar_timestamp": timestamp, "strategy_name": STRATEGY_NAME,
                "strategy_version": STRATEGY_VERSION, "parameters_hash": param_hash,
                "signal_type": evaluation.signal_type, "score": evaluation.score,
                "confidence": evaluation.confidence, "status": evaluation.status,
                "summary_zh": evaluation.summary_zh, "reasons_json": evaluation.reasons,
                "risks_json": evaluation.risks, "feature_refs_json": evaluation.feature_refs,
                "components_json": evaluation.components,
                "created_at": now, "updated_at": now,
            })
        statement = sqlite_insert(CandidateSignal)
        statement = statement.on_conflict_do_update(
            index_elements=[
                "symbol", "market", "timeframe", "bar_timestamp", "strategy_name",
                "strategy_version", "parameters_hash",
            ],
            set_={key: getattr(statement.excluded, key) for key in (
                "signal_type", "score", "confidence", "status", "summary_zh",
                "reasons_json", "risks_json", "feature_refs_json", "components_json",
                "updated_at",
            )},
        )
        self.db.execute(statement, rows)
        self.db.commit()
        return len(rows)

    def enabled_watchlist(self, symbols: Optional[Iterable[str]] = None) -> List[WatchlistItem]:
        query = select(WatchlistItem).where(WatchlistItem.enabled.is_(True))
        if symbols:
            query = query.where(WatchlistItem.symbol.in_([value.upper() for value in symbols]))
        return list(self.db.scalars(query.order_by(WatchlistItem.symbol)))

    def timeframe_enabled(self, item_id: int, timeframe: str) -> bool:
        return bool(self.db.scalar(select(WatchlistTimeframe.enabled).where(
            WatchlistTimeframe.watchlist_item_id == item_id,
            WatchlistTimeframe.timeframe == timeframe,
        )))
