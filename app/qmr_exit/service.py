from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.database.models import QmrExitEvaluation, QmrExitEvent, QmrMoneyFlowSnapshot
from app.qmr_exit.repository import QmrExitRepository
from app.qmr_exit.scoring import evaluate_exit, evaluate_money_flow
from app.market_context.gating import exit_context_adjustment
from app.market_context.service import MarketContextService


SECTOR_BENCHMARKS = {
    "Semiconductors": ("SOXX", "SMH"), "Information Technology": ("XLK", "QQQ"),
    "Software": ("IGV",), "Financials": ("XLF",), "Health Care": ("XLV",),
}


class QmrExitService:
    def __init__(self, db, settings, config_path=None):
        self.db, self.settings = db, settings
        self.repository = QmrExitRepository(db)
        path = config_path or getattr(settings, "qmr_exit_config_file", "config/qmr_exit_v1.yaml")
        self.config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    def run(self, symbol=None, evaluation_time=None, dry_run=False, limit=None):
        at = evaluation_time or datetime.now(timezone.utc)
        positions = self.repository.open_positions(symbol)
        if limit: positions = positions[:limit]
        output = {"scanned": len(positions), "created": 0, "skipped": 0, "failed": 0, "items": []}
        for position in positions:
            try:
                result = self.evaluate_position(position, at)
                if dry_run:
                    output["skipped"] += 1; output["items"].append(result); continue
                row, created = self.persist(position, at, result)
                output["created" if created else "skipped"] += 1
                output["items"].append(self.serialize(row))
            except Exception as exc:
                self.db.rollback(); output["failed"] += 1
                output["items"].append({"position_id": position.id, "symbol": position.symbol,
                                        "error": type(exc).__name__})
        return output

    def collect_money_flow(self, symbol, provider, trading_session="UNKNOWN"):
        payload = provider.fetch(symbol)
        at = payload.get("timestamp")
        if not isinstance(at, datetime): at = datetime.now(timezone.utc)
        raw = payload.get("raw") if payload.get("data_available") else None
        assessment = evaluate_money_flow(raw, config=self.config["money_flow"])
        row = QmrMoneyFlowSnapshot(symbol=symbol.upper().removeprefix("US."), timestamp=at,
            trading_session=trading_session, source=payload.get("source", "MOOMOO"),
            data_available=assessment["data_available"], raw_flow_json=raw or {},
            rolling_structure_json=assessment.get("rolling", {}), money_flow_regime=assessment["regime"],
            money_flow_score=assessment["money_flow_score"], accumulation_score=assessment["accumulation_score"],
            distribution_score=assessment["distribution_score"], absorption_score=assessment["absorption_score"],
            data_quality=payload.get("data_status", assessment.get("data_status", "UNAVAILABLE")))
        return self.repository.save_money_flow(row)

    def notify_pending(self, notifier, limit=100):
        output = {"scanned": 0, "sent": 0, "failed": 0}
        for event in self.repository.pending_events(limit):
            output["scanned"] += 1
            statuses = notifier.send_event(event)
            output["sent"] += sum(value == "SUCCESS" for value in statuses)
            output["failed"] += sum(value == "FAILED" for value in statuses)
        return output

    def evaluate_position(self, position, at):
        symbol = position.symbol.upper().removeprefix("US.")
        timeframes = {name: self.repository.bars(symbol, name, at) for name in ("1d", "60m", "30m")}
        daily = timeframes["1d"]
        if not daily:
            raise ValueError("NO_MARKET_DATA")
        flow_rows = self.repository.money_flow(symbol, at)
        raw = flow_rows[-1].raw_flow_json if flow_rows else None
        history = [row.raw_flow_json for row in flow_rows[:-1] if row.data_available]
        price_evidence = self._price_evidence(daily)
        money_flow = evaluate_money_flow(raw, price_evidence, history, self.config["money_flow"])
        benchmarks = {name: self.repository.bars(name, "1d", at) for name in ("SPY", "QQQ")}
        instrument = self.repository.instrument(symbol)
        benchmark_names = SECTOR_BENCHMARKS.get(getattr(instrument, "sector", None), ())
        selected_sector, sector_rows = None, []
        for name in benchmark_names:
            rows = self.repository.bars(name, "1d", at)
            if rows:
                selected_sector, sector_rows = name, rows
                break
        sector_universe = {}
        for names in SECTOR_BENCHMARKS.values():
            name = names[0]
            rows = self.repository.bars(name, "1d", at)
            if rows: sector_universe[name] = rows
        if sector_rows and selected_sector:
            sector_universe[selected_sector] = sector_rows
        previous = self.repository.previous(position.id)
        result = evaluate_exit(float(position.average_entry), float(position.highest_price),
            float(daily[-1].close), timeframes, benchmarks, sector_rows, sector_universe,
            money_flow, self.config, previous.state if previous else "HOLD")
        if getattr(self.settings, "market_context_enabled", False):
            context = MarketContextService(self.db, self.settings).current_for_symbol(symbol, at)
            adjustment = exit_context_adjustment(context["global"], context["sector"])
            result["details"]["market_context"] = {**context, **adjustment}
            if adjustment["risk_addition"]:
                result["exit_risk_score"] = min(100,
                    result["exit_risk_score"] + adjustment["risk_addition"])
                result["reasons"] = list(dict.fromkeys(
                    result["reasons"] + adjustment["reasons"]))
                if not result.get("hard_exit_reason"):
                    levels = self.config["state_thresholds"]
                    risk = result["exit_risk_score"]
                    result["state"] = ("EXIT" if risk >= levels["exit"] else
                        "REDUCE" if risk >= levels["reduce"] else
                        "PROTECT" if risk >= levels["protect"] else
                        "WATCH" if risk >= levels["watch"] else "HOLD")
        result["evaluated_price"] = float(daily[-1].close)
        return result

    def persist(self, position, at, result):
        existing = self.repository.existing(position.id, at, self.config["version"])
        if existing: return existing, False
        profit = result["details"]["profit_protection"]
        row = QmrExitEvaluation(
            position_id=position.id, strategy_code="quality_mispricing_recovery",
            strategy_version=position.strategy_version, parameter_version=self.config["version"],
            symbol=position.symbol.upper().removeprefix("US."), evaluation_time=at,
            entry_time=position.open_time, entry_price=position.average_entry,
            highest_price=position.highest_price, current_price=result["evaluated_price"],
            current_return=profit["current_return"], max_return=profit["max_return"],
            profit_giveback=profit["profit_giveback"], exit_risk_score=result["exit_risk_score"],
            capital_flow_risk=result["components"]["capital_flow"], trend_risk=result["components"]["trend"],
            relative_strength_risk=result["components"]["relative_strength"],
            sector_rotation_risk=result["components"]["sector_rotation"],
            profit_protection_risk=result["components"]["profit_protection"],
            exhaustion_risk=result["components"]["exhaustion"],
            money_flow_regime=result["details"]["money_flow"].get("regime", "NEUTRAL"),
            state=result["state"], previous_state=result["previous_state"], reduce_ratio=result["reduce_ratio"],
            dynamic_support=result["dynamic_support"], support_status=result["support_status"],
            exit_reason=result["exit_reason"], hard_exit_reason=result["hard_exit_reason"],
            reasons_json=result["reasons"], components_json=result["details"],
            data_quality_json={"money_flow_available": result["details"]["money_flow"].get("data_available", False),
                               "available_weight_pct": result["confidence"]},
            confidence=result["confidence"], model_version=self.config["version"])
        changed = row.state != row.previous_state
        significant = changed or (self.repository.previous(position.id) and
            abs(float(self.repository.previous(position.id).exit_risk_score) - result["exit_risk_score"]) >=
            self.config["notifications"]["score_change"])
        event = None
        if significant and row.state in self.config["notifications"]["states"]:
            event = QmrExitEvent(position_id=position.id, symbol=row.symbol, event_type="STATE_CHANGE" if changed else "RISK_CHANGE",
                previous_state=row.previous_state, state=row.state, reduce_ratio=row.reduce_ratio,
                event_time=at, reasons_json=row.reasons_json, notification_status="PENDING")
        return self.repository.save(row, event), True

    @staticmethod
    def _price_evidence(rows):
        if len(rows) < 3: return {}
        last, prior = rows[-1], rows[-2]
        span = max(float(last.high) - float(last.low), 1e-9)
        return {"rejected_lower": (float(last.close) - float(last.low)) / span >= .65,
                "higher_low": float(last.low) > float(prior.low),
                "vwap_reclaimed": False,
                "high_stall": float(last.close) <= float(prior.close) * 1.002,
                "upper_rejection": (float(last.high) - float(last.close)) / span >= .45}

    @staticmethod
    def serialize(row):
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}
