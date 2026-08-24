from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.recovery.repository import RecoveryRepository
from app.recovery.scoring import capital_flow, combine, context_recovery, stabilization, stage_and_entry, technical


class RecoveryService:
    def __init__(self, db, settings, config_path=None):
        self.db = db
        self.settings = settings
        self.config = yaml.safe_load(Path(config_path or settings.recovery_config_file).read_text(encoding="utf-8"))
        self.repository = RecoveryRepository(db)

    def run(self, evaluation_time=None, symbols=None, dry_run=False, limit=None):
        at = evaluation_time or datetime.now(timezone.utc)
        selected = [symbol.upper() for symbol in symbols] if symbols else None
        qmr_version = getattr(self.settings, "qmr_config_file", "config/qmr_v1.yaml")
        qmr_config = yaml.safe_load(Path(qmr_version).read_text(encoding="utf-8"))
        candidates = self.repository.watch_candidates(at, selected, limit, qmr_config["version"])
        result = {"evaluation_time": at, "scanned": len(candidates), "created": 0, "events": 0, "skipped": 0, "failed": 0, "items": []}
        for candidate in candidates:
            try:
                values, reasons = self.evaluate(candidate, at)
                if dry_run:
                    result["items"].append(self._serialize_values(values)); result["skipped"] += 1
                    continue
                row, created, changed = self.repository.save(values, reasons)
                result["created" if created else "skipped"] += 1
                result["events"] += int(changed)
                result["items"].append(self.serialize(row))
            except Exception as exc:
                self.db.rollback()
                result["failed"] += 1
                result["items"].append({"symbol": candidate.symbol, "error": type(exc).__name__})
        return result

    def evaluate(self, candidate, at):
        intervals = self.config["timeframes"]
        rows = {interval: self.repository.bars(candidate.symbol, interval, at) for interval in intervals}
        usable = {interval: values for interval, values in rows.items() if len(values) >= self.config["minimum_bars"]}
        if not usable or not rows.get("5m"):
            raise ValueError("INSUFFICIENT_RECOVERY_DATA")
        latest = rows["5m"][-1]
        current_session = [row for row in rows["5m"] if row.trading_date == latest.trading_date and row.market_session == latest.market_session]
        if not current_session:
            raise ValueError("NO_SESSION_DATA")
        s_score, s_components, low_recovery, stabilization_reasons = stabilization(usable, self.config)
        flow_score, flow_components, flow_reasons, flow_data = capital_flow(rows["5m"], self.config)
        technical_score, technical_components, technical_reasons = technical(rows.get("30m", []), self.config)
        universe = self.repository.universe(candidate.symbol)
        sector_candidates = self.config["sector_benchmarks"].get(
            None if universe is None else universe.sector,
            self.config["sector_benchmarks"]["default"],
        )
        sector_scores = []
        sector_sources = []
        for symbol in sector_candidates:
            benchmark_rows = self.repository.bars(symbol, "5m", at)
            value = context_recovery(benchmark_rows, self.config)
            if value is not None:
                sector_scores.append(value); sector_sources.append(symbol)
        sector_score = round(sum(sector_scores) / len(sector_scores)) if sector_scores else None
        market_scores = []
        for symbol in ("QQQ", "SPY"):
            value = context_recovery(self.repository.bars(symbol, "5m", at), self.config)
            if value is not None: market_scores.append(value)
        market_score = round(sum(market_scores) / len(market_scores)) if market_scores else None
        market_state = self._market_state(market_score)
        global_score = None
        recovery_score, coverage_weight = combine({
            "stabilization": s_score, "capital_flow": flow_score, "technical": technical_score,
            "sector": sector_score, "market": market_score,
        }, self.config)
        previous = self.repository.previous(candidate.symbol, at)
        session_low = min(float(row.low) for row in current_session)
        session_high = max(float(row.high) for row in current_session)
        stage, entry, failure = stage_and_entry(recovery_score, s_score, previous, session_low, self.config)
        available_timeframes = len(usable)
        confidence = "HIGH" if coverage_weight >= .9 and available_timeframes >= 3 and flow_data == "FULL" else ("MEDIUM" if coverage_weight >= .75 and available_timeframes >= 2 else "LOW")
        reasons = stabilization_reasons + flow_reasons + technical_reasons
        if sector_score is not None: reasons.append("板块修复评分 %s" % sector_score)
        if market_score is not None: reasons.append("大盘修复评分 %s" % market_score)
        if failure: reasons.append(failure)
        components = {
            "stabilization": s_components, "capital_flow": flow_components,
            "technical": technical_components, "sector": {"score": sector_score, "symbols": sector_sources},
            "market": {"score": market_score, "state": market_state},
            "global_context": {"score": None, "status": "UNKNOWN"},
            "available_timeframes": sorted(usable), "reasons": reasons,
        }
        values = {
            "qmr_candidate_id": candidate.id, "symbol": candidate.symbol, "evaluation_time": at,
            "price": float(latest.close), "session_low": session_low, "session_high": session_high,
            "low_recovery_pct": low_recovery, "stabilization_score": s_score,
            "capital_flow_score": flow_score, "technical_score": technical_score,
            "sector_recovery_score": sector_score, "market_recovery_score": market_score,
            "global_context_score": global_score, "recovery_score": recovery_score,
            "recovery_stage": stage, "entry_status": entry, "market_state": market_state,
            "trading_session": latest.market_session, "capital_flow_data": flow_data,
            "score_components_json": components,
            "data_sources_json": ["QMR:%s" % candidate.id, "MARKET_BARS"] + ["SECTOR:%s" % symbol for symbol in sector_sources],
            "data_confidence": confidence, "model_version": self.config["version"],
            "failure_reason": failure,
        }
        return values, reasons

    @staticmethod
    def _market_state(score):
        if score is None: return "UNKNOWN"
        if score < 25: return "MARKET_PANIC"
        if score < 50: return "MARKET_STABILIZING"
        if score < 75: return "MARKET_RECOVERY"
        return "MARKET_NORMAL"

    def list(self, **kwargs):
        kwargs["model_version"] = self.config["version"]
        rows, total = self.repository.latest(**kwargs)
        return [self.serialize(row) for row in rows], total

    def detail(self, symbol):
        return [self.serialize(row) for row in self.repository.history(symbol)]

    def event_history(self, symbol):
        return [{"id": row.id, "event_time": row.event_time, "previous_stage": row.previous_stage,
                 "recovery_stage": row.recovery_stage, "previous_entry_status": row.previous_entry_status,
                 "entry_status": row.entry_status, "price": str(row.price), "reasons": row.reason_json}
                for row in self.repository.events(symbol)]

    @staticmethod
    def _serialize_values(values):
        return {key: value for key, value in values.items() if key != "qmr_candidate_id"}

    @staticmethod
    def serialize(row):
        return {"id": row.id, "symbol": row.symbol, "timestamp": row.evaluation_time,
                "price": str(row.price), "session_low": str(row.session_low), "session_high": str(row.session_high),
                "low_recovery_pct": str(row.low_recovery_pct), "stabilization_score": row.stabilization_score,
                "capital_flow_score": row.capital_flow_score, "technical_score": row.technical_score,
                "sector_recovery_score": row.sector_recovery_score, "market_recovery_score": row.market_recovery_score,
                "global_context_score": row.global_context_score, "recovery_score": row.recovery_score,
                "recovery_stage": row.recovery_stage, "entry_status": row.entry_status,
                "market_state": row.market_state, "trading_session": row.trading_session,
                "capital_flow_data": row.capital_flow_data, "score_components": row.score_components_json,
                "data_sources": row.data_sources_json, "data_confidence": row.data_confidence,
                "model_version": row.model_version, "failure_reason": row.failure_reason,
                "last_update": row.created_at}
