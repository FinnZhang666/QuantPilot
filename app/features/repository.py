from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.enums import FeatureQualityStatus, FeatureValueType
from app.database.models import (
    FeatureCalculationJob,
    FeatureDefinitionRecord,
    FeatureQualityIssue,
    FeatureValueRecord,
    Instrument,
    MarketBar,
    RealtimeBar,
)
from app.features.models import FeatureDefinition, FeatureValue


class FeatureRepository:
    def __init__(self, db: Session, write_batch_size: int = 1000, read_chunk_size: int = 10000):
        self.db = db
        self.write_batch_size = write_batch_size
        self.read_chunk_size = read_chunk_size

    def initialize_definitions(self, definitions: Iterable[FeatureDefinition]) -> int:
        count = 0
        for item in definitions:
            statement = sqlite_insert(FeatureDefinitionRecord).values(
                feature_name=item.feature_name, display_name_zh=item.display_name_zh,
                category=item.category, description=item.description,
                value_type=item.value_type.value,
                default_parameters_json=item.default_parameters or {},
                required_bars=item.required_bars,
                supported_intervals_json=list(item.supported_intervals),
                requires_reference_symbol=item.requires_reference_symbol,
                reference_symbol=item.reference_symbol, version=item.version,
                is_active=True, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["feature_name", "version"],
                set_={"display_name_zh": item.display_name_zh, "description": item.description, "updated_at": datetime.now(timezone.utc)},
            )
            self.db.execute(statement)
            count += 1
        self.db.commit()
        return count

    def load_bars(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        realtime: bool = False,
    ) -> pd.DataFrame:
        model = RealtimeBar if realtime else MarketBar
        query = select(model).where(model.symbol == symbol, model.interval == interval)
        if realtime:
            query = query.where(model.is_closed.is_(True), model.data_source == "MOOMOO")
        else:
            query = query.where(model.adjustment_type == "FORWARD", model.data_source == "MOOMOO")
        if start:
            query = query.where(model.timestamp_utc >= start)
        if end:
            query = query.where(model.timestamp_utc <= end)
        chunks = list(self._frames_from_query(query.order_by(model.timestamp_utc)))
        return pd.concat(chunks) if chunks else pd.DataFrame()

    def _frames_from_query(self, query):
        """流式读取ORM行，避免一次把整表对象加载到Session身份映射。"""
        rows = self.db.scalars(query.execution_options(yield_per=self.read_chunk_size))
        batch = []
        for row in rows:
            batch.append({
                "timestamp_utc": row.timestamp_utc, "open": row.open, "high": row.high,
                "low": row.low, "close": row.close, "volume": row.volume,
                "turnover": row.turnover, "trading_date": row.trading_date,
                "market_session": row.market_session,
            })
            if len(batch) >= self.read_chunk_size:
                yield self._bar_frame(batch)
                batch = []
        if batch:
            yield self._bar_frame(batch)

    @staticmethod
    def _bar_frame(rows) -> pd.DataFrame:
        frame = pd.DataFrame(rows)
        frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
        return frame.set_index("timestamp_utc")

    def upsert_values(self, values: List[FeatureValue]) -> Tuple[int, int]:
        if not values:
            return 0, 0
        first = values[0]
        existing = self.db.scalar(select(func.count()).select_from(FeatureValueRecord).where(
            FeatureValueRecord.symbol == first.symbol,
            FeatureValueRecord.interval == first.interval.value,
            FeatureValueRecord.feature_name == first.feature_name,
            FeatureValueRecord.feature_version == first.feature_version,
            FeatureValueRecord.parameters_hash == first.parameters_hash,
            FeatureValueRecord.data_source == first.data_source,
            FeatureValueRecord.timestamp_utc >= min(item.timestamp_utc for item in values),
            FeatureValueRecord.timestamp_utc <= max(item.timestamp_utc for item in values),
        )) or 0
        instruments = dict(self.db.execute(select(Instrument.symbol, Instrument.id).where(Instrument.symbol.in_({item.symbol for item in values}))).all())
        rows = []
        for item in values:
            row = {
                "instrument_id": instruments[item.symbol], "symbol": item.symbol,
                "interval": item.interval.value, "timestamp_utc": item.timestamp_utc,
                "feature_name": item.feature_name, "feature_version": item.feature_version,
                "parameters_hash": item.parameters_hash, "value_decimal": None,
                "value_integer": None, "value_boolean": None, "value_text": None,
                "quality_status": item.quality_status.value,
                "quality_message": item.quality_message,
                "source_bar_timestamp": item.source_bar_timestamp,
                "data_source": item.data_source, "calculated_at": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
            }
            if item.value_type == FeatureValueType.DECIMAL:
                row["value_decimal"] = item.value
            elif item.value_type == FeatureValueType.INTEGER:
                row["value_integer"] = item.value
            elif item.value_type == FeatureValueType.BOOLEAN:
                row["value_boolean"] = item.value
            else:
                row["value_text"] = item.value
            rows.append(row)
        for index in range(0, len(rows), self.write_batch_size):
            batch = rows[index:index + self.write_batch_size]
            statement = sqlite_insert(FeatureValueRecord)
            statement = statement.on_conflict_do_update(
                index_elements=["symbol", "interval", "timestamp_utc", "feature_name", "feature_version", "parameters_hash", "data_source"],
                set_={key: getattr(statement.excluded, key) for key in (
                    "value_decimal", "value_integer", "value_boolean", "value_text",
                    "quality_status", "quality_message", "source_bar_timestamp",
                    "calculated_at", "updated_at",
                )},
            )
            self.db.execute(statement, batch)
        self.db.commit()
        return max(0, len(rows) - existing), min(len(rows), existing)

    def latest_timestamp(self, symbol: str, interval: str, feature_name: str, data_source: str) -> Optional[datetime]:
        return self.db.scalar(select(func.max(FeatureValueRecord.timestamp_utc)).where(
            FeatureValueRecord.symbol == symbol, FeatureValueRecord.interval == interval,
            FeatureValueRecord.feature_name == feature_name,
            FeatureValueRecord.data_source == data_source,
        ))

    def record_issue(self, symbol: str, interval: str, feature_name: str, issue_type: str, message: str, timestamp: Optional[datetime] = None, severity: str = "WARNING") -> None:
        existing = self.db.scalar(select(FeatureQualityIssue.id).where(
            FeatureQualityIssue.symbol == symbol,
            FeatureQualityIssue.interval == interval,
            FeatureQualityIssue.feature_name == feature_name,
            FeatureQualityIssue.issue_type == issue_type,
            FeatureQualityIssue.resolved_at.is_(None),
        ).limit(1))
        if existing:
            return
        self.db.add(FeatureQualityIssue(
            symbol=symbol, interval=interval, timestamp_utc=timestamp,
            feature_name=feature_name, feature_version="1.0.0",
            issue_type=issue_type, severity=severity, message=message,
        ))
        self.db.commit()
