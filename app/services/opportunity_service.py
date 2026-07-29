from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.models import (
    CandidatePoolEntry, CandidateSignal, MarketBar, MarketRegime, Opportunity, RealtimeBar,
)

VALID_DIRECTIONS = {"LONG", "SHORT"}
VALID_STATUSES = {
    "DETECTED", "NOTIFIED", "ACTIVE", "EXPIRED", "INVALIDATED", "CLOSED",
    "REVIEW_PENDING", "REVIEWED", "REVIEW_FAILED",
}


class OpportunityService:
    def __init__(self, db: Session, min_score: int = 70, expiry_bars: int = 3):
        self.db = db
        self.min_score = min_score
        self.expiry_bars = expiry_bars
        self.last_invalidated: List[Opportunity] = []

    def from_signal(self, signal: CandidateSignal, direction: str = "LONG") -> Tuple[Optional[Opportunity], bool]:
        self.last_invalidated = []
        if direction not in VALID_DIRECTIONS:
            raise ValueError("Opportunity方向必须是LONG或SHORT。")
        if signal.signal_type in {"CANDIDATE_EXIT", "CANDIDATE_REDUCE"}:
            self.invalidate_for_signal(signal)
            return None, False
        if signal.signal_type != "CANDIDATE_BUY" or signal.score < self.min_score:
            return None, False
        existing = self.db.scalar(select(Opportunity).where(
            Opportunity.symbol == signal.symbol, Opportunity.timeframe == signal.timeframe,
            Opportunity.strategy_name == signal.strategy_name,
            Opportunity.strategy_version == signal.strategy_version,
            Opportunity.direction == direction, Opportunity.bar_time == signal.bar_timestamp,
        ))
        if existing:
            return existing, False
        active = self.db.scalar(select(Opportunity).where(
            Opportunity.symbol == signal.symbol, Opportunity.timeframe == signal.timeframe,
            Opportunity.strategy_name == signal.strategy_name,
            Opportunity.strategy_version == signal.strategy_version,
            Opportunity.direction == direction,
            Opportunity.status.in_(["DETECTED", "NOTIFIED", "ACTIVE"]),
        ).order_by(desc(Opportunity.bar_time)).limit(1))
        signal_time = self._aware(signal.bar_timestamp)
        if active and (active.expiry_at is None or self._aware(active.expiry_at) > signal_time):
            active.status = "ACTIVE"
            active.decision_snapshot_json = {
                "confirmed_by_signal_id": signal.id,
                "confirmed_at_bar_time": signal_time.isoformat(),
                "score": signal.score, "confidence": signal.confidence,
            }
            self.db.commit()
            return active, False
        price = self._reference_price(signal)
        if price is None:
            return None, False
        now = datetime.now(timezone.utc)
        candidate = self.db.scalar(select(CandidatePoolEntry).where(
            CandidatePoolEntry.symbol == signal.symbol,
            CandidatePoolEntry.status.in_(["CANDIDATE", "RESEARCHING", "QUALIFIED"]),
            CandidatePoolEntry.direction.in_([direction, "BOTH"]),
        ).order_by(desc(CandidatePoolEntry.pool_date), CandidatePoolEntry.rank).limit(1))
        regime = self.db.scalar(select(MarketRegime).order_by(
            desc(MarketRegime.bar_time),
        ).limit(1))
        opportunity = Opportunity(
            symbol=signal.symbol, timeframe=signal.timeframe, direction=direction,
            opportunity_type="PULLBACK_RESTRENGTH",
            strategy_name=signal.strategy_name, strategy_version=signal.strategy_version,
            signal_id=signal.id, status="DETECTED", score=signal.score,
            candidate_pool_entry_id=candidate.id if candidate else None,
            market_regime_id=regime.id if regime else None,
            market_regime=regime.regime if regime else None,
            confidence=signal.confidence, detected_at=now,
            bar_time=self._aware(signal.bar_timestamp),
            entry_reference_price=price,
            expiry_at=self._expiry(self._aware(signal.bar_timestamp), signal.timeframe),
            feature_snapshot_json={
                "feature_refs": signal.feature_refs_json,
                "parameters_hash": signal.parameters_hash,
            },
            strategy_snapshot_json={
                "signal_type": signal.signal_type, "status": signal.status,
                "summary_zh": signal.summary_zh, "reasons": signal.reasons_json,
                "risks": signal.risks_json, "components": signal.components_json,
                "score": signal.score, "confidence": signal.confidence,
            },
            decision_snapshot_json=None, notification_status="PENDING",
        )
        opportunity.decision_snapshot_json = {
            "candidate_pool": {
                "entry_id": candidate.id, "direction": candidate.direction,
                "final_score": candidate.final_score,
                "sources": (candidate.reason_snapshot_json or {}).get("sources", []),
            } if candidate else None,
            "market_regime": {
                "id": regime.id, "regime": regime.regime,
                "long_bias": regime.long_bias, "short_bias": regime.short_bias,
            } if regime else {"regime": "UNKNOWN"},
        }
        self.db.add(opportunity)
        self.db.commit()
        self._ensure_research(opportunity.id)
        return opportunity, True

    def convert_latest(self, symbol: str, timeframe: str) -> Tuple[Optional[Opportunity], bool]:
        signal = self.db.scalar(select(CandidateSignal).where(
            CandidateSignal.symbol == symbol.upper().replace("US.", ""),
            CandidateSignal.timeframe == timeframe,
        ).order_by(desc(CandidateSignal.bar_timestamp), desc(CandidateSignal.id)).limit(1))
        return self.from_signal(signal) if signal else (None, False)

    def update_status(self, opportunity_id: int, status: str, message_id: Optional[str] = None) -> Opportunity:
        if status not in VALID_STATUSES:
            raise ValueError("Opportunity状态无效。")
        row = self.db.get(Opportunity, opportunity_id)
        if row is None:
            raise KeyError("Opportunity不存在。")
        row.status = status
        if status == "NOTIFIED":
            row.notification_status = "SENT"
            row.notification_message_id = message_id
        self.db.commit()
        self._ensure_research(row.id)
        return row

    def mark_notification_failed(self, opportunity_id: int, error: str) -> None:
        row = self.db.get(Opportunity, opportunity_id)
        if row:
            row.notification_status = "FAILED"
            snapshot = dict(row.decision_snapshot_json or {})
            snapshot["notification_error"] = error
            row.decision_snapshot_json = snapshot
            self.db.commit()

    def invalidate_for_signal(self, signal: CandidateSignal) -> int:
        rows = self.db.scalars(select(Opportunity).where(
            Opportunity.symbol == signal.symbol,
            Opportunity.timeframe == signal.timeframe,
            Opportunity.status.in_(["DETECTED", "NOTIFIED", "ACTIVE"]),
        )).all()
        self.last_invalidated = list(rows)
        for row in rows:
            row.status = "INVALIDATED"
            row.decision_snapshot_json = {
                "invalidated_by_signal_id": signal.id,
                "signal_type": signal.signal_type,
                "bar_time": self._aware(signal.bar_timestamp).isoformat(),
                "summary_zh": signal.summary_zh,
            }
        self.db.commit()
        for row in rows:
            self._ensure_research(row.id)
        return len(rows)

    def expire_due(self, now: Optional[datetime] = None) -> List[Opportunity]:
        now = now or datetime.now(timezone.utc)
        rows = self.db.scalars(select(Opportunity).where(
            Opportunity.expiry_at.is_not(None), Opportunity.expiry_at <= now,
            Opportunity.status.in_(["DETECTED", "NOTIFIED", "ACTIVE"]),
        )).all()
        for row in rows:
            row.status = "EXPIRED"
        self.db.commit()
        for row in rows:
            self._ensure_research(row.id)
        return rows

    def recent(self, limit: int = 10, symbol: Optional[str] = None) -> List[Opportunity]:
        query = select(Opportunity)
        if symbol:
            query = query.where(Opportunity.symbol == symbol.upper().replace("US.", ""))
        return list(self.db.scalars(query.order_by(desc(Opportunity.detected_at)).limit(limit)))

    def _reference_price(self, signal: CandidateSignal) -> Optional[Decimal]:
        full_symbol = "US." + signal.symbol.replace("US.", "")
        realtime = self.db.scalar(select(RealtimeBar.close).where(
            RealtimeBar.symbol == full_symbol, RealtimeBar.interval == signal.timeframe,
            RealtimeBar.timestamp_utc == signal.bar_timestamp, RealtimeBar.is_closed.is_(True),
        ).limit(1))
        if realtime is not None:
            return Decimal(realtime)
        historical = self.db.scalar(select(MarketBar.close).where(
            MarketBar.symbol == full_symbol, MarketBar.interval == signal.timeframe,
            MarketBar.timestamp_utc == signal.bar_timestamp,
            MarketBar.adjustment_type == "FORWARD", MarketBar.data_source == "MOOMOO",
        ).limit(1))
        return Decimal(historical) if historical is not None else None

    def _expiry(self, bar_time: datetime, timeframe: str) -> datetime:
        minutes: Dict[str, int] = {
            "1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1d": 1440,
        }
        return bar_time + timedelta(minutes=minutes[timeframe] * self.expiry_bars)

    def _ensure_research(self, opportunity_id: int) -> None:
        try:
            from app.research.service import ResearchService
            ResearchService(self.db).ensure_workspace(opportunity_id)
        except Exception:
            # Research是旁路能力，不得阻断Opportunity Runtime。
            self.db.rollback()

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
