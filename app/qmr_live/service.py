import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import desc, func, select

from app.database.models import (
    QmrLiveSignal, QmrSignalParticipation, QmrSignalPerformance,
    TelegramFeedbackRecord, TelegramRuntimeUser,
)
from app.qmr_live.repository import QmrLiveRepository
from app.qmr_live.telegram import QmrTelegramNotifier
from app.telegram_runtime.transport import TelegramBotTransport


LEVEL_ORDER = {"EARLY_ENTRY": 1, "CONFIRMED_ENTRY": 2, "STRONG_ENTRY": 3}


class QmrLiveSignalService:
    def __init__(self, db, settings, notifier=None):
        self.db, self.settings = db, settings
        self.config = yaml.safe_load(Path(settings.qmr_live_config_file).read_text(encoding="utf-8"))
        self.repository = QmrLiveRepository(db)
        self.notifier = notifier or QmrTelegramNotifier(self.repository, settings,
            TelegramBotTransport(settings.telegram_timeout_seconds, settings.telegram_max_retries))

    def run(self, evaluation_time=None):
        at = self.utc(evaluation_time or datetime.now(timezone.utc))
        from app.strategy.qmr_registry import StrategyCenterRepository
        strategy = StrategyCenterRepository(self.db).ensure_qmr()
        if not strategy.is_enabled:
            return {"strategy_status": "DISABLED", "scanned": 0, "created": 0,
                    "upgraded": 0, "invalidated": 0, "skipped": 0, "notifications": []}
        run = self.repository.latest_strategy_run()
        strategy_status = run.strategy_status if run else "RESEARCH"
        parameter_set_id = run.parameter_set_id if run else None
        result = {"strategy_status": strategy_status, "scanned": 0, "created": 0,
                  "upgraded": 0, "invalidated": 0, "skipped": 0, "notifications": []}
        for score in self.repository.latest_scores():
            result["scanned"] += 1
            recovery = self.repository.recovery(score)
            active = self.repository.active_signal(score.symbol)
            if recovery and recovery.recovery_stage == "FAILED_RECOVERY" and active:
                active.status, active.latest_price = "INVALIDATED", recovery.price
                active.invalidation_reason_json = [recovery.failure_reason or "修复结构失效"]
                active.last_state_change_at, active.completed_at = at, at
                self.repository.commit()
                result["notifications"] += self.notifier.send(active, "INVALIDATED")
                result["invalidated"] += 1; continue
            if strategy_status == "REJECTED" or score.buy_status not in LEVEL_ORDER:
                result["skipped"] += 1; continue
            if at - self.utc(score.evaluation_time) > timedelta(minutes=self.config["max_signal_age_minutes"]):
                result["skipped"] += 1; continue
            if active:
                if LEVEL_ORDER[score.buy_status] <= LEVEL_ORDER[active.signal_level]:
                    result["skipped"] += 1; continue
                active.previous_level, active.signal_level = active.signal_level, score.buy_status
                active.buy_score_id, active.buy_score, active.buy_grade = score.id, score.final_buy_score, score.buy_grade
                active.recovery_score, active.latest_price = score.recovery_score, score.entry_reference_price
                active.last_state_change_at = at
                active.signal_snapshot_json = self.snapshot(score, recovery)
                active.similar_statistics_json = self.similar_statistics(score, recovery)
                self.repository.commit()
                result["notifications"] += self.notifier.send(active, score.buy_status)
                result["upgraded"] += 1; continue
            latest = self.repository.latest_signal(score.symbol)
            if latest and at - self.utc(latest.last_state_change_at) < timedelta(
                    minutes=self.config["cooldown_minutes"]):
                result["skipped"] += 1; continue
            signal = self.create_signal(score, recovery, strategy_status, parameter_set_id, at)
            self.repository.save_signal(signal)
            signal.status = "ACTIVE"; self.repository.commit()
            result["notifications"] += self.notifier.send(signal, score.buy_status)
            result["created"] += 1
        return result

    def create_signal(self, score, recovery, strategy_status, parameter_set_id, at):
        et = at.astimezone(ZoneInfo("America/New_York")); prefix = "QMR-%s-" % et.strftime("%Y%m%d")
        sequence = self.repository.next_sequence(prefix)
        instrument = self.repository.instrument(score.symbol)
        session = recovery.trading_session if recovery else "UNKNOWN"
        confidence = score.data_confidence
        if session in ("OVERNIGHT", "PRE_MARKET", "AFTER_HOURS") and confidence == "HIGH": confidence = "MEDIUM"
        return QmrLiveSignal(signal_id=prefix + "%03d" % sequence, buy_score_id=score.id,
            parameter_set_id=parameter_set_id, symbol=score.symbol, signal_level=score.buy_status,
            signal_mode="LIVE" if strategy_status == "VALIDATED" else "PAPER", status="OPEN",
            strategy_status=strategy_status, strategy_version="QMR-v1.0", model_version=score.model_version,
            telegram_template_version=self.config["telegram_template_version"], signal_time=at,
            signal_price=score.entry_reference_price, latest_price=score.entry_reference_price,
            buy_score=score.final_buy_score, buy_grade=score.buy_grade,
            quality_score=score.quality_score, mispricing_score=score.mispricing_score,
            recovery_score=score.recovery_score,
            market_state=recovery.market_state if recovery else None,
            sector=instrument.sector if instrument else None, trading_session=session,
            session_confidence=confidence, chase_risk_level=score.chase_risk_level,
            similar_statistics_json=self.similar_statistics(score, recovery),
            signal_snapshot_json=self.snapshot(score, recovery), last_state_change_at=at)

    @staticmethod
    def snapshot(score, recovery):
        reasons = [] if recovery is None else (recovery.score_components_json or {}).get("reasons", [])
        return {"buy_score_id": score.id, "evaluation_time": score.evaluation_time.isoformat(),
            "buy_components": score.score_components_json, "recovery_components": None if recovery is None else recovery.score_components_json,
            "reasons": reasons, "data_confidence": score.data_confidence}

    def similar_statistics(self, score, recovery):
        cases = self.repository.similar_cases()
        if not cases: return {"status": "UNAVAILABLE", "sample_count": 0}
        instrument = self.repository.instrument(score.symbol); sector = instrument.sector if instrument else None
        ranked = sorted(cases, key=lambda case: self.distance(case, score, recovery, sector))[:self.config["similarity_limit"]]
        def values(field, key): return [float(getattr(case, field).get(key)) for case in ranked if getattr(case, field).get(key) is not None]
        r5, r10, mae, mfe = values("returns_json", "5d"), values("returns_json", "10d"), values("mae_json", "10d"), values("mfe_json", "10d")
        return {"status": "AVAILABLE", "sample_count": len(ranked),
            "win_rate_5d": sum(value > 0 for value in r5) / len(r5) if r5 else None,
            "average_return_5d": mean(r5) if r5 else None, "average_return_10d": mean(r10) if r10 else None,
            "mae": mean(mae) if mae else None, "mfe": mean(mfe) if mfe else None}

    def distance(self, case, score, recovery, sector):
        weights = self.config["similarity_fields"]
        value = weights["quality_score"] * abs(case.quality_score - score.quality_score) / 100
        value += weights["mispricing_score"] * abs(case.mispricing_score - score.mispricing_score) / 100
        value += weights["recovery_score"] * abs(case.recovery_score - score.recovery_score) / 100
        value += weights["buy_score"] * abs(case.buy_score - score.final_buy_score) / 100
        value += weights["market_state"] * (case.market_state != (recovery.market_state if recovery else None))
        value += weights["sector"] * (case.sector != sector)
        return value

    def feedback(self, user, signal_id, helpful, bot_alias):
        signal = self.required(signal_id); row = self.repository.feedback(user.id, signal.signal_id)
        category = "HELPFUL" if helpful else "NOT_HELPFUL"
        if row is None:
            row = TelegramFeedbackRecord(user_id=user.id, bot_alias=bot_alias, language=user.language,
                category=category, message=category, related_type="QMR_SIGNAL", related_id=signal.signal_id)
            self.db.add(row)
        else: row.category, row.message = category, category
        self.db.commit(); return row

    def bought(self, user, signal_id):
        signal = self.required(signal_id); row = self.repository.participation(user.telegram_user_id, signal.signal_id)
        if row: return row, False
        row = QmrSignalParticipation(telegram_user_id=user.telegram_user_id, chat_id=user.chat_id,
            signal_id=signal.signal_id, symbol=signal.symbol, entry_price=signal.signal_price,
            entry_price_source="SIGNAL_REFERENCE", user_action_time=datetime.now(timezone.utc), status="OPEN")
        self.db.add(row); self.db.commit(); return row, True

    def required(self, signal_id):
        row = self.repository.signal(signal_id)
        if row is None: raise KeyError("QMR Signal不存在。")
        return row

    def query(self, signal_id):
        signal = self.required(signal_id)
        return signal, self.repository.performances(signal.signal_id)

    def resolve_reply(self, chat_id, message_id):
        row = self.repository.delivery_by_message(chat_id, message_id)
        return None if row is None else row.signal_id

    @staticmethod
    def utc(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
