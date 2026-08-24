from sqlalchemy import desc, select

from app.database.models import (
    MarketBar, QmrExitEvaluation, QmrExitEvent, QmrMoneyFlowSnapshot,
    SystemPaperPosition, UniverseInstrument,
)


class QmrExitRepository:
    def __init__(self, db):
        self.db = db

    def open_positions(self, symbol=None):
        query = select(SystemPaperPosition).where(SystemPaperPosition.status == "OPEN")
        if symbol:
            query = query.where(SystemPaperPosition.symbol.in_((symbol, "US." + symbol)))
        return list(self.db.scalars(query.order_by(SystemPaperPosition.id)))

    def bars(self, symbol, timeframe, at, limit=260):
        bare = symbol.upper().removeprefix("US.")
        return list(reversed(list(self.db.scalars(select(MarketBar).where(
            MarketBar.symbol.in_((bare, "US." + bare)), MarketBar.interval == timeframe,
            MarketBar.timestamp_utc <= at, MarketBar.is_blank.is_(False),
        ).order_by(desc(MarketBar.timestamp_utc)).limit(limit)))))

    def money_flow(self, symbol, at, limit=10):
        return list(reversed(list(self.db.scalars(select(QmrMoneyFlowSnapshot).where(
            QmrMoneyFlowSnapshot.symbol == symbol.upper(), QmrMoneyFlowSnapshot.timestamp <= at,
        ).order_by(desc(QmrMoneyFlowSnapshot.timestamp)).limit(limit)))))

    def instrument(self, symbol):
        return self.db.scalar(select(UniverseInstrument).where(
            UniverseInstrument.symbol == symbol.upper().removeprefix("US.")))

    def previous(self, position_id):
        return self.db.scalar(select(QmrExitEvaluation).where(
            QmrExitEvaluation.position_id == position_id,
        ).order_by(desc(QmrExitEvaluation.evaluation_time)).limit(1))

    def save_money_flow(self, row):
        existing = self.db.scalar(select(QmrMoneyFlowSnapshot).where(
            QmrMoneyFlowSnapshot.symbol == row.symbol,
            QmrMoneyFlowSnapshot.timestamp == row.timestamp,
            QmrMoneyFlowSnapshot.source == row.source))
        if existing: return existing, False
        self.db.add(row); self.db.commit(); return row, True

    def existing(self, position_id, at, model_version):
        return self.db.scalar(select(QmrExitEvaluation).where(
            QmrExitEvaluation.position_id == position_id,
            QmrExitEvaluation.evaluation_time == at,
            QmrExitEvaluation.model_version == model_version,
        ))

    def save(self, evaluation, event=None):
        self.db.add(evaluation); self.db.flush()
        if event is not None:
            event.evaluation_id = evaluation.id
            self.db.add(event)
        self.db.commit()
        return evaluation

    def list(self, symbol=None, state=None, limit=100):
        query = select(QmrExitEvaluation)
        if symbol: query = query.where(QmrExitEvaluation.symbol == symbol.upper())
        if state: query = query.where(QmrExitEvaluation.state == state.upper())
        return list(self.db.scalars(query.order_by(desc(QmrExitEvaluation.evaluation_time)).limit(limit)))

    def pending_events(self, limit=100):
        return list(self.db.scalars(select(QmrExitEvent).where(
            QmrExitEvent.notification_status == "PENDING").order_by(QmrExitEvent.event_time).limit(limit)))
