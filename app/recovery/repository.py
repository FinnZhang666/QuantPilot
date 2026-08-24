from sqlalchemy import desc, func, or_, select

from app.database.models import MarketBar, QmrCandidateRecord, RecoveryEventRecord, RecoveryScoreRecord, UniverseInstrument


class RecoveryRepository:
    def __init__(self, db):
        self.db = db

    def watch_candidates(self, evaluation_time, symbols=None, limit=None, model_version=None):
        base_filters = [QmrCandidateRecord.evaluation_time <= evaluation_time]
        if model_version:
            base_filters.append(QmrCandidateRecord.model_version == model_version)
        latest = select(
            QmrCandidateRecord.symbol,
            func.max(QmrCandidateRecord.evaluation_time).label("latest"),
        ).where(*base_filters).group_by(QmrCandidateRecord.symbol).subquery()
        query = select(QmrCandidateRecord).join(
            latest,
            (QmrCandidateRecord.symbol == latest.c.symbol) &
            (QmrCandidateRecord.evaluation_time == latest.c.latest),
        ).where(QmrCandidateRecord.candidate_status == "WATCH")
        if model_version:
            query = query.where(QmrCandidateRecord.model_version == model_version)
        if symbols:
            query = query.where(QmrCandidateRecord.symbol.in_(symbols))
        query = query.order_by(QmrCandidateRecord.symbol)
        if limit:
            query = query.limit(limit)
        return list(self.db.scalars(query))

    def universe(self, symbol):
        return self.db.scalar(select(UniverseInstrument).where(UniverseInstrument.symbol == symbol))

    def bars(self, symbol, interval, evaluation_time, limit=2500):
        bare = symbol.upper().removeprefix("US.")
        aliases = (bare, "US." + bare)
        rows = list(self.db.scalars(select(MarketBar).where(
            MarketBar.symbol.in_(aliases), MarketBar.interval == interval,
            MarketBar.timestamp_utc <= evaluation_time, MarketBar.is_blank.is_(False),
        ).order_by(desc(MarketBar.timestamp_utc)).limit(limit)))
        deduplicated = {}
        for row in reversed(rows):
            deduplicated[row.timestamp_utc] = row
        return [deduplicated[key] for key in sorted(deduplicated)]

    def previous(self, symbol, evaluation_time):
        return self.db.scalar(select(RecoveryScoreRecord).where(
            RecoveryScoreRecord.symbol == symbol,
            RecoveryScoreRecord.evaluation_time < evaluation_time,
        ).order_by(desc(RecoveryScoreRecord.evaluation_time)).limit(1))

    def save(self, values, reasons):
        existing = self.db.scalar(select(RecoveryScoreRecord).where(
            RecoveryScoreRecord.symbol == values["symbol"],
            RecoveryScoreRecord.evaluation_time == values["evaluation_time"],
            RecoveryScoreRecord.model_version == values["model_version"],
        ))
        if existing:
            return existing, False, False
        previous = self.previous(values["symbol"], values["evaluation_time"])
        row = RecoveryScoreRecord(**values)
        self.db.add(row)
        self.db.flush()
        changed = previous is None or previous.recovery_stage != row.recovery_stage or previous.entry_status != row.entry_status
        if changed:
            self.db.add(RecoveryEventRecord(
                recovery_score_id=row.id, symbol=row.symbol, event_time=row.evaluation_time,
                previous_stage=None if previous is None else previous.recovery_stage,
                recovery_stage=row.recovery_stage,
                previous_entry_status=None if previous is None else previous.entry_status,
                entry_status=row.entry_status, price=row.price, reason_json=reasons,
                model_version=row.model_version,
            ))
        self.db.commit()
        return row, True, changed

    def latest(self, symbol=None, entry_status=None, stage=None, limit=100, offset=0, model_version=None):
        base_filters = []
        if model_version:
            base_filters.append(RecoveryScoreRecord.model_version == model_version)
        latest = select(
            RecoveryScoreRecord.symbol,
            func.max(RecoveryScoreRecord.evaluation_time).label("latest"),
        ).where(*base_filters).group_by(RecoveryScoreRecord.symbol).subquery()
        query = select(RecoveryScoreRecord).join(
            latest,
            (RecoveryScoreRecord.symbol == latest.c.symbol) &
            (RecoveryScoreRecord.evaluation_time == latest.c.latest),
        )
        if model_version: query = query.where(RecoveryScoreRecord.model_version == model_version)
        if symbol: query = query.where(RecoveryScoreRecord.symbol == symbol.upper())
        if entry_status: query = query.where(RecoveryScoreRecord.entry_status == entry_status.upper())
        if stage: query = query.where(RecoveryScoreRecord.recovery_stage == stage.upper())
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = list(self.db.scalars(query.order_by(desc(RecoveryScoreRecord.recovery_score), RecoveryScoreRecord.symbol).offset(offset).limit(limit)))
        return rows, total

    def history(self, symbol, limit=100):
        return list(self.db.scalars(select(RecoveryScoreRecord).where(
            RecoveryScoreRecord.symbol == symbol.upper(),
        ).order_by(desc(RecoveryScoreRecord.evaluation_time)).limit(limit)))

    def events(self, symbol, limit=100):
        return list(self.db.scalars(select(RecoveryEventRecord).where(
            RecoveryEventRecord.symbol == symbol.upper(),
        ).order_by(desc(RecoveryEventRecord.event_time)).limit(limit)))

    def latest_evaluation_time(self):
        return self.db.scalar(select(func.max(RecoveryScoreRecord.evaluation_time)))
