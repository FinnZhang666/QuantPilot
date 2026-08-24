from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from app.buy_score.repository import BuyScoreRepository
from app.buy_score.scoring import STATUS_ORDER, calculate, combined_confidence


class BuyScoreService:
    def __init__(self, db, settings, config_path=None):
        self.db = db
        self.settings = settings
        self.config = yaml.safe_load(Path(config_path or settings.buy_score_config_file).read_text(encoding="utf-8"))
        self.qmr_config = yaml.safe_load(Path(settings.qmr_config_file).read_text(encoding="utf-8"))
        self.recovery_config = yaml.safe_load(Path(settings.recovery_config_file).read_text(encoding="utf-8"))
        self.repository = BuyScoreRepository(db)

    def run(self, evaluation_time=None, symbols=None, dry_run=False, limit=None):
        at = evaluation_time or datetime.now(timezone.utc)
        selected = [symbol.upper() for symbol in symbols] if symbols else None
        eligible = self.repository.eligible(at, self.qmr_config["version"], self.recovery_config["version"], selected, limit)
        result = {"evaluation_time": at, "scanned": len(eligible), "created": 0, "skipped": 0, "failed": 0, "ranked": 0, "items": []}
        if not dry_run:
            self.repository.sync_mappings(self.config.get("instrument_mappings", []))
        for qmr, recovery in eligible:
            try:
                values = self.evaluate(qmr, recovery, at)
                if dry_run:
                    result["items"].append(self._serialize_values(values)); result["skipped"] += 1
                else:
                    row, created = self.repository.save(values)
                    result["created" if created else "skipped"] += 1
                    result["items"].append(self.serialize(row))
            except Exception as exc:
                self.db.rollback(); result["failed"] += 1
                result["items"].append({"symbol": qmr.symbol, "error": type(exc).__name__})
        if not dry_run:
            ranked = self.repository.rank(at, self.config["version"])
            result["ranked"] = len(ranked)
            result["items"] = [self.serialize(row) for row in ranked]
        return result

    def evaluate(self, qmr, recovery, at):
        previous = self.repository.previous(qmr.symbol, at, self.config["version"])
        recovery_signal_price = self.repository.recovery_signal_price(qmr.symbol, at, self.recovery_config["version"])
        features = self._risk_features(qmr.symbol, at, recovery)
        returns = qmr.score_components_json.get("mispricing", {}).get("returns", {})
        known_drawdowns = [float(value) for value in returns.values() if value is not None]
        features["recent_max_drawdown_pct"] = abs(min(known_drawdowns) * 100) if known_drawdowns else None
        quality_components = qmr.score_components_json.get("quality", {})
        importance = quality_components.get("etf_importance", {})
        etf_score = None
        if importance.get("max"):
            etf_score = round(100 * importance.get("score", 0) / importance["max"])
        confidence = combined_confidence(qmr.data_confidence, recovery.data_confidence)
        inputs = {
            "quality_score": qmr.quality_score, "mispricing_score": qmr.mispricing_score,
            "recovery_score": recovery.recovery_score, "sector_score": recovery.sector_recovery_score,
            "market_score": recovery.market_recovery_score, "etf_importance_score": etf_score,
            "fundamental_risk": qmr.fundamental_risk, "recovery_stage": recovery.recovery_stage,
            "market_state": recovery.market_state, "data_confidence": confidence,
            "current_price": float(recovery.price), "recovery_signal_price": None if recovery_signal_price is None else float(recovery_signal_price),
            "volatility": features,
        }
        scored = calculate(inputs, self.config, previous, at)
        entry_low, entry_high = self._entry_zone(float(recovery.price), features.get("vwap"),
            features.get("atr"), float(recovery.session_low), float(recovery.session_high))
        discoveries = self._first_prices(previous, scored["buy_status"], float(recovery.price))
        components = scored.pop("components")
        components.update({"recovery_stage": recovery.recovery_stage,
            "recovery_entry_status": recovery.entry_status, "feature_risk": features,
            "qmr_model_version": qmr.model_version, "recovery_model_version": recovery.model_version})
        return {
            "qmr_candidate_id": qmr.id, "recovery_score_id": recovery.id,
            "symbol": qmr.symbol, "evaluation_time": at,
            "quality_score": qmr.quality_score, "mispricing_score": qmr.mispricing_score,
            "recovery_score": recovery.recovery_score, "sector_score": recovery.sector_recovery_score,
            "market_score": recovery.market_recovery_score, "etf_importance_score": etf_score,
            **scored, "entry_reference_price": recovery.price,
            "entry_zone_low": entry_low, "entry_zone_high": entry_high, **discoveries,
            "rank_current": None, "rank_previous": None, "rank_change": None,
            "holding_profile": "UNKNOWN", "data_confidence": confidence,
            "model_version": self.config["version"], "score_components_json": components,
        }

    def _risk_features(self, symbol, at, recovery):
        def numeric(row):
            return None if row is None or row.value_decimal is None else float(row.value_decimal)
        atr = numeric(self.repository.feature(symbol, "1d", "atr_14", at))
        atr_pct = numeric(self.repository.feature(symbol, "1d", "atr_pct_14", at))
        realized = numeric(self.repository.feature(symbol, "1d", "realized_volatility_20", at))
        vwap = numeric(self.repository.feature(symbol, "5m", "session_vwap_regular", at, timedelta(days=1)))
        price = float(recovery.price)
        intraday = (float(recovery.session_high) / float(recovery.session_low) - 1) * 100 if float(recovery.session_low) > 0 else None
        return {"atr": atr, "atr_pct": atr_pct, "realized_volatility": realized,
                "intraday_range_pct": intraday, "vwap": vwap,
                "source": "FEATURE_VALUES"}

    def _entry_zone(self, current, vwap, atr, session_low, session_high):
        rules = self.config["entry_zone"]
        anchor = current if vwap is None else (current + vwap) / 2
        anchor = min(session_high, max(session_low, anchor))
        width = atr * rules["atr_multiple"] if atr is not None else (session_high - session_low) * rules["session_range_fraction"]
        return max(session_low, anchor - width), min(session_high, anchor + width)

    @staticmethod
    def _first_prices(previous, status, price):
        result = {"first_watch_price": None, "first_early_entry_price": None,
                  "first_confirmed_entry_price": None, "first_strong_entry_price": None}
        if previous is not None:
            for key in result: result[key] = getattr(previous, key)
        thresholds = (("WATCH", "first_watch_price"), ("EARLY_ENTRY", "first_early_entry_price"),
                      ("CONFIRMED_ENTRY", "first_confirmed_entry_price"), ("STRONG_ENTRY", "first_strong_entry_price"))
        for required, key in thresholds:
            if result[key] is None and STATUS_ORDER.get(status, -1) >= STATUS_ORDER[required]: result[key] = price
        return result

    def list(self, **kwargs):
        kwargs["model_version"] = self.config["version"]
        rows, total = self.repository.latest(**kwargs)
        return [self.serialize(row) for row in rows], total

    def detail(self, symbol):
        return [self.serialize(row) for row in self.repository.history(symbol, self.config["version"])]

    def mappings(self, symbol):
        database = self.repository.mapping(symbol)
        rows = database or [type("Mapping", (), item)() for item in self.config.get("instrument_mappings", []) if item["underlying_symbol"] == symbol.upper() and item["active"]]
        return [{"underlying_symbol": row.underlying_symbol, "leveraged_symbol": row.leveraged_symbol,
                 "leverage_multiple": str(row.leverage_multiple), "direction": row.direction,
                 "provider": row.provider, "active": row.active} for row in rows]

    @staticmethod
    def _serialize_values(values):
        return {key: value for key, value in values.items() if key not in ("qmr_candidate_id", "recovery_score_id")}

    @staticmethod
    def serialize(row):
        return {"id": row.id, "symbol": row.symbol, "timestamp": row.evaluation_time,
            "quality_score": row.quality_score, "mispricing_score": row.mispricing_score,
            "recovery_score": row.recovery_score, "sector_score": row.sector_score,
            "market_score": row.market_score, "etf_importance_score": row.etf_importance_score,
            "raw_buy_score": row.raw_buy_score, "risk_penalty": row.risk_penalty,
            "final_buy_score": row.final_buy_score, "buy_grade": row.buy_grade,
            "buy_status": row.buy_status, "recommended_action": row.recommended_action,
            "entry_reference_price": str(row.entry_reference_price),
            "entry_zone_low": None if row.entry_zone_low is None else str(row.entry_zone_low),
            "entry_zone_high": None if row.entry_zone_high is None else str(row.entry_zone_high),
            "first_watch_price": None if row.first_watch_price is None else str(row.first_watch_price),
            "first_early_entry_price": None if row.first_early_entry_price is None else str(row.first_early_entry_price),
            "first_confirmed_entry_price": None if row.first_confirmed_entry_price is None else str(row.first_confirmed_entry_price),
            "first_strong_entry_price": None if row.first_strong_entry_price is None else str(row.first_strong_entry_price),
            "rank_current": row.rank_current, "rank_previous": row.rank_previous, "rank_change": row.rank_change,
            "chase_risk_score": row.chase_risk_score, "chase_risk_level": row.chase_risk_level,
            "entry_attractiveness": row.entry_attractiveness,
            "recommended_position_confidence": row.recommended_position_confidence,
            "holding_profile": row.holding_profile, "cooldown_until": row.cooldown_until,
            "data_confidence": row.data_confidence, "model_version": row.model_version,
            "score_components": row.score_components_json, "last_update": row.created_at}
