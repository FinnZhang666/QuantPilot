from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.database.models import MarketContextSnapshot, SectorContextSnapshot
from app.market_context.repository import MarketContextRepository
from app.market_context.scoring import global_score, sector_score


class MarketContextService:
    def __init__(self, db, settings, config_path=None):
        self.db, self.settings = db, settings
        path = config_path or settings.market_context_config_file
        self.config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self.repository = MarketContextRepository(db)

    def evaluate(self, at=None, session="UNKNOWN", persist=True):
        at = self._aware(at or datetime.now(timezone.utc))
        global_value, global_row = self.evaluate_global(at, session, persist)
        sectors = {}
        for sector in self.repository.sectors():
            value, _ = self.evaluate_sector(sector, at, session, persist)
            sectors[sector] = value
        if persist: self.db.commit()
        return {"global": global_value, "sectors": sectors,
                "timestamp": at, "model_version": self.config["version"]}

    def evaluate_global(self, at, session="UNKNOWN", persist=True):
        series, timestamps = {}, {}
        for symbol in self.config["global"]["assets"]:
            series[symbol], timestamp = self.repository.closes(symbol, at)
            timestamps[symbol] = timestamp.isoformat() if timestamp else None
        value = global_score(series, self.config["global"])
        value.update({"timestamp": at, "session": session,
                      "model_version": self.config["version"], "source_timestamps": timestamps})
        row = None
        if persist:
            row = MarketContextSnapshot(timestamp=at, session=session,
                global_score=value["global_score"], global_state=value["global_state"],
                asset_scores_json=value["asset_scores"], source_timestamps_json=timestamps,
                data_quality_json={"coverage": value["coverage"],
                                   "data_sufficient": value["data_sufficient"]},
                model_version=self.config["version"])
            row, _ = self.repository.save_global(row)
        return value, row

    def evaluate_sector(self, sector, at, session="UNKNOWN", persist=True):
        benchmarks = self.benchmarks(sector)
        primary = next((symbol for symbol in benchmarks if self.repository.closes(symbol, at)[0]), benchmarks[0])
        sector_closes, timestamp = self.repository.closes(primary, at)
        spy, _ = self.repository.closes("SPY", at)
        qqq, _ = self.repository.closes("QQQ", at)
        breadth, breadth_count = self.repository.breadth(sector, at)
        value = sector_score(sector_closes, spy, qqq, breadth, self.config["sector"]["states"])
        value.update({"sector_code": sector, "benchmark": primary,
                      "secondary_benchmark": next((x for x in benchmarks if x != primary), None),
                      "timestamp": at, "session": session, "flow_score": None,
                      "breadth_count": breadth_count, "model_version": self.config["version"],
                      "data_sufficient": len(sector_closes) >= self.config["sector"]["minimum_bars"]})
        row = None
        if persist:
            relative = value["relative"]
            row = SectorContextSnapshot(timestamp=at, session=session, sector_code=sector,
                benchmark=primary, secondary_benchmark=value["secondary_benchmark"],
                sector_score=value["sector_score"], sector_state=value["sector_state"],
                rs_1d=relative[1], rs_3d=relative[3], rs_5d=relative[5],
                rs_10d=relative[10], rs_20d=relative[20], breadth=breadth,
                flow_score=None, rotation_score=value["rotation_score"],
                data_quality_json={"data_sufficient": value["data_sufficient"],
                                   "breadth_count": breadth_count,
                                   "source_timestamp": timestamp.isoformat() if timestamp else None},
                model_version=self.config["version"])
            row, _ = self.repository.save_sector(row)
        return value, row

    def current_for_symbol(self, symbol, at=None):
        at = self._aware(at or datetime.now(timezone.utc))
        instrument = self.repository.instrument(symbol)
        sector = getattr(instrument, "sector", None) or "default"
        global_row = self.repository.latest_global(at)
        sector_row = self.repository.latest_sector(sector, at)
        return {"global": self.serialize_global(global_row),
                "sector": self.serialize_sector(sector_row), "sector_code": sector}

    def reconstruct(self, timestamps, session="HISTORICAL", persist=True):
        output = {"scanned": 0, "created": 0, "failed": 0}
        for at in timestamps:
            try:
                result = self.evaluate(at, session, persist)
                output["scanned"] += 1
                output["created"] += 1
                output.setdefault("items", []).append(result)
            except Exception:
                self.db.rollback(); output["failed"] += 1
        return output

    def benchmarks(self, sector):
        mapping = self.config["sector"]["benchmarks"]
        return mapping.get(sector, mapping["default"])

    @staticmethod
    def serialize_global(row):
        if row is None: return None
        return {"id": row.id, "timestamp": row.timestamp, "session": row.session,
                "global_score": row.global_score, "global_state": row.global_state,
                "asset_scores": row.asset_scores_json, "data_quality": row.data_quality_json,
                "model_version": row.model_version}

    @staticmethod
    def serialize_sector(row):
        if row is None: return None
        return {"id": row.id, "timestamp": row.timestamp, "session": row.session,
                "sector_code": row.sector_code, "benchmark": row.benchmark,
                "secondary_benchmark": row.secondary_benchmark,
                "sector_score": row.sector_score, "sector_state": row.sector_state,
                "relative_strength": {"1d": row.rs_1d, "3d": row.rs_3d, "5d": row.rs_5d,
                                      "10d": row.rs_10d, "20d": row.rs_20d},
                "breadth": row.breadth, "flow_score": row.flow_score,
                "rotation_score": row.rotation_score, "data_quality": row.data_quality_json,
                "model_version": row.model_version}

    @staticmethod
    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
