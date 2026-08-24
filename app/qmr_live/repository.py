from datetime import timezone

from sqlalchemy import desc, func, select

from app.database.models import (
    BuyScoreRecord, MarketBar, QmrBacktestCase, QmrBacktestRun, QmrLiveSignal,
    QmrSignalDelivery, QmrSignalParticipation, QmrSignalPerformance,
    RecoveryScoreRecord, TelegramAdminRecord, TelegramFeedbackRecord,
    TelegramRuntimeUser, UniverseInstrument,
)


class QmrLiveRepository:
    def __init__(self, db): self.db = db

    def latest_strategy_run(self):
        return self.db.scalar(select(QmrBacktestRun).where(
            QmrBacktestRun.status == "SUCCESS").order_by(desc(QmrBacktestRun.id)).limit(1))

    def latest_scores(self):
        latest = select(BuyScoreRecord.symbol, func.max(BuyScoreRecord.evaluation_time).label("at")).group_by(
            BuyScoreRecord.symbol).subquery()
        return list(self.db.scalars(select(BuyScoreRecord).join(latest,
            (BuyScoreRecord.symbol == latest.c.symbol) & (BuyScoreRecord.evaluation_time == latest.c.at))))

    def recovery(self, score): return self.db.get(RecoveryScoreRecord, score.recovery_score_id)
    def instrument(self, symbol): return self.db.scalar(select(UniverseInstrument).where(UniverseInstrument.symbol == symbol))

    def active_signal(self, symbol):
        return self.db.scalar(select(QmrLiveSignal).where(QmrLiveSignal.symbol == symbol,
            QmrLiveSignal.status.in_(("OPEN", "ACTIVE"))).order_by(desc(QmrLiveSignal.id)).limit(1))

    def latest_signal(self, symbol):
        return self.db.scalar(select(QmrLiveSignal).where(
            QmrLiveSignal.symbol == symbol).order_by(desc(QmrLiveSignal.last_state_change_at)).limit(1))

    def signal(self, signal_id):
        return self.db.scalar(select(QmrLiveSignal).where(QmrLiveSignal.signal_id == signal_id.upper().lstrip("#")))

    def next_sequence(self, prefix):
        return (self.db.scalar(select(func.count()).select_from(QmrLiveSignal).where(
            QmrLiveSignal.signal_id.like(prefix + "%"))) or 0) + 1

    def similar_cases(self):
        run = self.latest_strategy_run()
        if run is None:
            return []
        return list(self.db.scalars(select(QmrBacktestCase).where(
            QmrBacktestCase.run_id == run.id,
            QmrBacktestCase.result != "INSUFFICIENT_DATA")))

    def save_signal(self, row): self.db.add(row); self.db.commit(); return row
    def commit(self): self.db.commit()

    def delivery(self, signal_id, chat_id, event_type):
        return self.db.scalar(select(QmrSignalDelivery).where(QmrSignalDelivery.signal_id == signal_id,
            QmrSignalDelivery.chat_id == chat_id, QmrSignalDelivery.event_type == event_type))

    def delivery_by_message(self, chat_id, message_id):
        return self.db.scalar(select(QmrSignalDelivery).where(QmrSignalDelivery.chat_id == chat_id,
            QmrSignalDelivery.telegram_message_id == str(message_id)).order_by(desc(QmrSignalDelivery.id)).limit(1))

    def save_delivery(self, row): self.db.add(row); self.db.commit(); return row

    def recipients(self, research):
        if research:
            rows = self.db.scalars(select(TelegramAdminRecord).where(
                TelegramAdminRecord.enabled.is_(True), TelegramAdminRecord.telegram_user_id.is_not(None)))
            return [{"chat_id": str(row.telegram_user_id), "language": "zh-CN", "bot_alias": None} for row in rows]
        rows = self.db.scalars(select(TelegramRuntimeUser).where(TelegramRuntimeUser.status == "ACTIVE"))
        return [{"chat_id": row.chat_id, "language": row.language, "bot_alias": row.last_bot_alias} for row in rows]

    def feedback(self, user_id, signal_id):
        return self.db.scalar(select(TelegramFeedbackRecord).where(
            TelegramFeedbackRecord.user_id == user_id,
            TelegramFeedbackRecord.related_type == "QMR_SIGNAL",
            TelegramFeedbackRecord.related_id == signal_id,
            TelegramFeedbackRecord.category.in_(("HELPFUL", "NOT_HELPFUL"))))

    def participation(self, telegram_user_id, signal_id):
        return self.db.scalar(select(QmrSignalParticipation).where(
            QmrSignalParticipation.telegram_user_id == telegram_user_id,
            QmrSignalParticipation.signal_id == signal_id))

    def performances(self, signal_id):
        return list(self.db.scalars(select(QmrSignalPerformance).where(
            QmrSignalPerformance.signal_id == signal_id).order_by(QmrSignalPerformance.window_days)))

    def bars(self, signal, end):
        names = (signal.symbol, "US." + signal.symbol)
        return list(self.db.scalars(select(MarketBar).where(MarketBar.symbol.in_(names),
            MarketBar.interval == "1d", MarketBar.timestamp_utc > signal.signal_time,
            MarketBar.timestamp_utc <= end, MarketBar.is_blank.is_(False)).order_by(MarketBar.timestamp_utc)))

    def signals(self, statuses=None):
        query = select(QmrLiveSignal)
        if statuses: query = query.where(QmrLiveSignal.status.in_(statuses))
        return list(self.db.scalars(query.order_by(QmrLiveSignal.signal_time)))

    def list_signals(self, symbol=None, level=None, status=None, limit=100, offset=0):
        query = select(QmrLiveSignal)
        if symbol: query = query.where(QmrLiveSignal.symbol == symbol.upper())
        if level: query = query.where(QmrLiveSignal.signal_level == level.upper())
        if status: query = query.where(QmrLiveSignal.status == status.upper())
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self.db.scalars(query.order_by(desc(QmrLiveSignal.signal_time)).offset(offset).limit(limit))
        return list(rows), total

    def feedback_counts(self, signal_id):
        rows = self.db.execute(select(TelegramFeedbackRecord.category, func.count()).where(
            TelegramFeedbackRecord.related_type == "QMR_SIGNAL",
            TelegramFeedbackRecord.related_id == signal_id,
        ).group_by(TelegramFeedbackRecord.category))
        return {category: count for category, count in rows}

    @staticmethod
    def aware(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
