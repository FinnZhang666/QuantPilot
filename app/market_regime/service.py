from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import yaml
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import FeatureValueRecord, MarketBar, MarketRegime
from app.market_regime.scoring import MarketRegimeScorer


def load_config(path: str) -> Dict[str, object]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict) or not {"version", "thresholds", "weights"} <= set(value):
        raise ValueError("Market Regime配置文件格式无效。")
    return value


class MarketRegimeService:
    FEATURE_NAMES = tuple(MarketRegimeScorer.REQUIRED) + ("realized_volatility_20",)

    def __init__(self, db: Session, settings: Settings, config_path="config/market_regime_v1.yaml"):
        self.db = db
        self.settings = settings
        self.config = load_config(config_path)
        self.scorer = MarketRegimeScorer(self.config)

    def current(self, market="US", timeframe=None) -> Optional[MarketRegime]:
        return self.db.scalar(select(MarketRegime).where(
            MarketRegime.market == market,
            MarketRegime.timeframe == (timeframe or self.settings.market_regime_timeframe),
        ).order_by(desc(MarketRegime.bar_time)).limit(1))

    def evaluate(self, force=False) -> MarketRegime:
        timeframe = self.settings.market_regime_timeframe
        snapshots = {}
        latest_bar = None
        for symbol in (
            self.settings.market_regime_benchmark,
            self.settings.market_regime_sector_benchmark,
            self.settings.market_regime_risk_symbol,
        ):
            snapshot = self._latest_features(symbol, timeframe)
            snapshots[symbol] = snapshot
            timestamp = snapshot.get("_timestamp")
            if timestamp and (latest_bar is None or timestamp > latest_bar):
                latest_bar = timestamp
        latest_bar = latest_bar or datetime.now(timezone.utc).replace(microsecond=0)
        existing = self.db.scalar(select(MarketRegime).where(
            MarketRegime.market == "US", MarketRegime.timeframe == timeframe,
            MarketRegime.bar_time == latest_bar,
        ))
        if existing and not force:
            return existing
        result = self.scorer.score(snapshots, latest_bar)
        row = existing or MarketRegime(
            market="US", timeframe=timeframe, bar_time=result.bar_time,
            benchmark_symbol=self.settings.market_regime_benchmark,
            sector_benchmark_symbol=self.settings.market_regime_sector_benchmark,
        )
        row.regime = result.regime
        row.trend_score = result.trend_score
        row.breadth_score = result.breadth_score
        row.momentum_score = result.momentum_score
        row.volatility_score = result.volatility_score
        row.risk_score = result.risk_score
        row.long_bias = result.long_bias
        row.short_bias = result.short_bias
        row.confidence = result.confidence
        row.evaluated_at = datetime.now(timezone.utc)
        row.valid_until = row.evaluated_at + timedelta(minutes=self.settings.market_regime_cache_minutes)
        row.feature_snapshot_json = _json_safe(result.features)
        row.reason_snapshot_json = {
            "reasons": result.reasons, "risks": result.risks,
            "data_sufficient": result.data_sufficient,
            "config_version": result.config_version,
            "breadth_source": "UNAVAILABLE",
        }
        self.db.add(row)
        self.db.commit()
        return row

    def _latest_features(self, symbol: str, timeframe: str) -> Dict[str, object]:
        full = "US." + symbol.replace("US.", "")
        count = self.db.scalar(select(func.count()).select_from(MarketBar).where(
            MarketBar.symbol == full, MarketBar.interval == timeframe,
            MarketBar.adjustment_type == "FORWARD", MarketBar.data_source == "MOOMOO",
        )) or 0
        latest = self.db.scalar(select(func.max(FeatureValueRecord.timestamp_utc)).where(
            FeatureValueRecord.symbol == full, FeatureValueRecord.interval == timeframe,
            FeatureValueRecord.feature_name.in_(self.FEATURE_NAMES),
            FeatureValueRecord.quality_status == "VALID",
        ))
        if latest is None or count < self.settings.market_regime_min_bars:
            return {"_bar_count": count}
        rows = self.db.scalars(select(FeatureValueRecord).where(
            FeatureValueRecord.symbol == full, FeatureValueRecord.interval == timeframe,
            FeatureValueRecord.timestamp_utc == latest,
            FeatureValueRecord.feature_name.in_(self.FEATURE_NAMES),
            FeatureValueRecord.quality_status == "VALID",
        ).order_by(desc(FeatureValueRecord.id))).all()
        output = {"_timestamp": latest, "_bar_count": count}
        for row in rows:
            output.setdefault(row.feature_name, _feature_value(row))
        return output


def _feature_value(row):
    if row.value_decimal is not None:
        return float(row.value_decimal)
    if row.value_integer is not None:
        return row.value_integer
    if row.value_boolean is not None:
        return row.value_boolean
    return row.value_text


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
