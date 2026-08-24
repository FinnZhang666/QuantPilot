from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.candidate_pool.expiry import expire_due
from app.candidate_pool.filters import evaluate_filters
from app.candidate_pool.ranking import CandidateRanker
from app.candidate_pool.universe import DatabaseUniverseProvider
from app.core.config import Settings
from app.database.models import (
    CandidatePoolEntry, CandidatePoolRun, FeatureValueRecord,
    MarketRegime, WatchlistItem,
)
from app.market_regime.service import MarketRegimeService


FEATURE_NAMES = (
    "close_vs_ema20_pct", "ema20_vs_ema60_pct", "ema20_slope_5",
    "breakout_high_20_pct", "distance_from_low_20_pct",
    "relative_return_qqq_20", "relative_return_soxx_20",
    "volume_ratio_20", "return_1", "atr_pct_14",
)


def load_candidate_config(path="config/candidate_pool_v1.yaml"):
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not {"version", "thresholds", "weights"} <= set(value):
        raise ValueError("Candidate Pool配置文件格式无效。")
    return value


class CandidatePoolService:
    def __init__(self, db: Session, settings: Settings, config_path="config/candidate_pool_v1.yaml"):
        self.db = db
        self.settings = settings
        self.config = load_candidate_config(config_path)
        self.ranker = CandidateRanker(
            settings.candidate_pool_min_score,
            settings.candidate_pool_both_score_gap,
        )

    def current_regime(self) -> Optional[MarketRegime]:
        return self.db.scalar(select(MarketRegime).where(
            MarketRegime.market == "US",
            MarketRegime.timeframe == self.settings.market_regime_timeframe,
        ).order_by(desc(MarketRegime.bar_time)).limit(1))

    def build(self, run_type="MANUAL", pool_date=None, refresh=False) -> CandidatePoolRun:
        running = self.db.scalar(select(CandidatePoolRun).where(
            CandidatePoolRun.run_type == run_type,
            CandidatePoolRun.status == "RUNNING",
        ).limit(1))
        if running:
            return running
        run = CandidatePoolRun(run_type=run_type, market="US", status="RUNNING")
        self.db.add(run)
        self.db.commit()
        day = (pool_date or date.today()).isoformat()
        errors = []
        candidates = []
        try:
            regime = self.current_regime()
            if regime is None and self.settings.market_regime_enabled:
                try:
                    regime = MarketRegimeService(self.db, self.settings).evaluate()
                except Exception as exc:
                    self.db.rollback()
                    errors.append({"symbol": "MARKET", "error": type(exc).__name__})
            universe = DatabaseUniverseProvider(self.db).get_symbols()
            run.universe_size = len(universe)
            watchlist = {
                row.symbol: row for row in self.db.scalars(select(WatchlistItem).where(
                    WatchlistItem.enabled.is_(True),
                ))
            }
            for item in universe:
                try:
                    features = self._latest_features(item.symbol)
                    filters = evaluate_filters(features, self.config, item.symbol in watchlist)
                    ranked = self.ranker.rank_one(filters, regime)
                    run.scanned_size += 1
                    if not ranked["direction"] or not ranked["data_sufficient"]:
                        continue
                    candidates.append((item, features, filters, ranked))
                except Exception as exc:
                    errors.append({"symbol": item.symbol, "error": type(exc).__name__ + "：" + str(exc)})
                    self.db.rollback()
            candidates.sort(key=lambda row: (-row[3]["final_score"], row[0].symbol))
            selected = self._apply_capacity(candidates)
            now = datetime.now(timezone.utc)
            for rank, (item, features, filters, ranked) in enumerate(selected, 1):
                sources = sorted(set(item.source.split(",")))
                source_type = sources[0] if len(sources) == 1 else "SYSTEM"
                benchmark = (
                    item.benchmark or
                    ("SOXX" if (item.sector or "").lower() == "semiconductor" else "QQQ")
                )
                statement = sqlite_insert(CandidatePoolEntry).values(
                    symbol=item.symbol, market=item.market, asset_type=item.asset_type,
                    direction=ranked["direction"], source_type=source_type,
                    source_reference=",".join(sources), pool_date=day,
                    status="CANDIDATE", long_score=ranked["long_score"],
                    short_score=ranked["short_score"], final_score=ranked["final_score"],
                    rank=rank, market_regime_id=regime.id if regime else None,
                    benchmark_symbol=benchmark,
                    sector_benchmark_symbol="SOXX" if benchmark == "SOXX" else None,
                    reason_snapshot_json={
                        "reasons": ranked["reasons"], "risks": ranked["risks"],
                        "sources": sources, "ranking_version": self.config["version"],
                        "market_regime": regime.regime if regime else "UNKNOWN",
                        "regime_adjustment": ranked["regime_adjustment"],
                    },
                    filter_snapshot_json=ranked["components"],
                    feature_snapshot_json=features, first_seen_at=now, last_seen_at=now,
                    expires_at=now + timedelta(hours=self.settings.candidate_pool_expiry_hours),
                    created_at=now, updated_at=now,
                ).on_conflict_do_update(
                    index_elements=["symbol", "market", "pool_date"],
                    set_={
                        "direction": ranked["direction"], "source_type": source_type,
                        "source_reference": ",".join(sources),
                        "long_score": ranked["long_score"], "short_score": ranked["short_score"],
                        "final_score": ranked["final_score"], "rank": rank,
                        "market_regime_id": regime.id if regime else None,
                        "reason_snapshot_json": {
                            "reasons": ranked["reasons"], "risks": ranked["risks"],
                            "sources": sources, "ranking_version": self.config["version"],
                            "market_regime": regime.regime if regime else "UNKNOWN",
                            "regime_adjustment": ranked["regime_adjustment"],
                        },
                        "filter_snapshot_json": ranked["components"],
                        "feature_snapshot_json": features, "last_seen_at": now,
                        "expires_at": now + timedelta(hours=self.settings.candidate_pool_expiry_hours),
                        "updated_at": now,
                    },
                )
                self.db.execute(statement)
            expire_due(self.db)
            rows = list(self.db.scalars(select(CandidatePoolEntry).where(
                CandidatePoolEntry.pool_date == day,
                CandidatePoolEntry.status != "EXPIRED",
            )))
            run.candidate_count = len(rows)
            run.long_count = sum(row.direction == "LONG" for row in rows)
            run.short_count = sum(row.direction == "SHORT" for row in rows)
            run.both_count = sum(row.direction == "BOTH" for row in rows)
            run.regime_id = regime.id if regime else None
            run.error_count = len(errors)
            run.status = "DEGRADED" if errors else "COMPLETED"
            run.completed_at = datetime.now(timezone.utc)
            run.summary_json = {
                "pool_date": day, "errors": errors, "refresh": refresh,
                "config_version": self.config["version"],
                "regime": regime.regime if regime else "UNKNOWN",
            }
            self.db.commit()
            return run
        except Exception as exc:
            self.db.rollback()
            run = self.db.get(CandidatePoolRun, run.id)
            run.status = "FAILED"
            run.completed_at = datetime.now(timezone.utc)
            run.error_count = max(1, len(errors))
            run.summary_json = {"errors": errors + [{"error": type(exc).__name__ + "：" + str(exc)}]}
            self.db.commit()
            return run

    def refresh(self) -> CandidatePoolRun:
        return self.build("REALTIME", refresh=True)

    def run_daily_if_due(self, now=None) -> Optional[CandidatePoolRun]:
        if not self.settings.candidate_pool_daily_enabled:
            return None
        local_now = (now or datetime.now(timezone.utc)).astimezone(
            ZoneInfo(self.settings.candidate_pool_timezone)
        )
        hour, minute = (int(value) for value in self.settings.candidate_pool_daily_time.split(":", 1))
        if (local_now.hour, local_now.minute) < (hour, minute):
            return None
        day = local_now.date().isoformat()
        existing = self.db.scalar(select(CandidatePoolRun).where(
            CandidatePoolRun.run_type == "DAILY",
            func.json_extract(CandidatePoolRun.summary_json, "$.pool_date") == day,
            CandidatePoolRun.status.in_(["COMPLETED", "DEGRADED"]),
        ).limit(1))
        return existing or self.build("DAILY", local_now.date())

    def expire(self, entry_id: int) -> CandidatePoolEntry:
        row = self.db.get(CandidatePoolEntry, entry_id)
        if row is None:
            raise KeyError("候选池条目不存在。")
        row.status = "EXPIRED"
        row.expires_at = datetime.now(timezone.utc)
        self.db.commit()
        return row

    def _latest_features(self, symbol: str) -> Dict[str, object]:
        full = "US." + symbol.replace("US.", "")
        latest = self.db.scalar(select(func.max(FeatureValueRecord.timestamp_utc)).where(
            FeatureValueRecord.symbol == full,
            FeatureValueRecord.interval == self.settings.market_regime_timeframe,
            FeatureValueRecord.feature_name.in_(FEATURE_NAMES),
            FeatureValueRecord.quality_status == "VALID",
        ))
        if latest is None:
            return {}
        rows = self.db.scalars(select(FeatureValueRecord).where(
            FeatureValueRecord.symbol == full,
            FeatureValueRecord.interval == self.settings.market_regime_timeframe,
            FeatureValueRecord.timestamp_utc == latest,
            FeatureValueRecord.feature_name.in_(FEATURE_NAMES),
            FeatureValueRecord.quality_status == "VALID",
        ).order_by(desc(FeatureValueRecord.id))).all()
        output = {"_timestamp": latest.isoformat()}
        for row in rows:
            output.setdefault(row.feature_name, self._value(row))
        return output

    def _apply_capacity(self, candidates):
        selected = []
        long_count = short_count = 0
        for row in candidates:
            direction = row[3]["direction"]
            if len(selected) >= self.settings.candidate_pool_max_total:
                break
            if direction in {"LONG", "BOTH"} and long_count >= self.settings.candidate_pool_max_long:
                continue
            if direction in {"SHORT", "BOTH"} and short_count >= self.settings.candidate_pool_max_short:
                continue
            selected.append(row)
            long_count += direction in {"LONG", "BOTH"}
            short_count += direction in {"SHORT", "BOTH"}
        return selected

    @staticmethod
    def _value(row):
        if row.value_decimal is not None:
            return float(row.value_decimal)
        if row.value_integer is not None:
            return row.value_integer
        if row.value_boolean is not None:
            return row.value_boolean
        return row.value_text
