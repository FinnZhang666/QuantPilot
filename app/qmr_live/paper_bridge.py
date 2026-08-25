import hashlib
from decimal import Decimal

from sqlalchemy import select

from app.database.models import CandidateSignal, TradePlan
from app.trade_lifecycle.adapter import TradePlanAdapter
from app.trade_lifecycle.service import TradeLifecycleService


class QmrPaperBridge:
    """Projects a QMR signal into the existing TradePlan/Paper ledger; never calls a broker."""
    def __init__(self, db):
        self.db = db

    def ensure(self, signal):
        parameter_hash = hashlib.sha256((signal.strategy_version + ":" +
            str(signal.parameter_set_id or "default")).encode()).hexdigest()
        candidate = self.db.scalar(select(CandidateSignal).where(
            CandidateSignal.symbol == signal.symbol,
            CandidateSignal.market == signal.market,
            CandidateSignal.timeframe == "1d",
            CandidateSignal.bar_timestamp == signal.signal_time,
            CandidateSignal.strategy_name == "quality_mispricing_recovery",
            CandidateSignal.strategy_version == signal.strategy_version,
            CandidateSignal.parameters_hash == parameter_hash,
        ))
        if candidate is None:
            snapshot = signal.signal_snapshot_json or {}
            candidate = CandidateSignal(symbol=signal.symbol, market=signal.market, timeframe="1d",
                bar_timestamp=signal.signal_time, strategy_name="quality_mispricing_recovery",
                strategy_version=signal.strategy_version, parameters_hash=parameter_hash,
                signal_type="CANDIDATE_BUY", score=signal.buy_score,
                confidence={"HIGH": 90, "MEDIUM": 70, "LOW": 50}.get(signal.session_confidence, 50),
                status="VALID", summary_zh="QMR优质错杀修复产生介入信号。",
                reasons_json=snapshot.get("reasons", []), risks_json=[],
                feature_refs_json={"source": "qmr_live_signals", "signal_id": signal.signal_id},
                components_json={"quality": signal.quality_score, "mispricing": signal.mispricing_score,
                                 "recovery": signal.recovery_score, "buy_score": signal.buy_score,
                                 "qmr_signal_id": signal.signal_id,
                                 "market_context": snapshot.get("market_context")})
            self.db.add(candidate); self.db.flush()
        plan = self.db.scalar(select(TradePlan).where(
            TradePlan.signal_id == candidate.id, TradePlan.direction == "LONG"))
        if plan is None:
            draft = TradePlanAdapter().from_candidate_signal(
                candidate, reference_price=Decimal(str(signal.signal_price)))
            lifecycle = TradeLifecycleService(self.db)
            plan = lifecycle.create(draft)
            lifecycle.advance(plan.plan_id, "PLAN", "QMR Signal已确认并进入内部Paper验证。", "QMR_PAPER_BRIDGE",
                              {"qmr_signal_id": signal.signal_id})
            return plan, True
        return plan, False
