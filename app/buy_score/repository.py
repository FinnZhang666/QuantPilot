from sqlalchemy import case, desc, func, select

from app.database.models import (
    BuyRankingRecord, BuyScoreRecord, FeatureValueRecord, InstrumentMapping,
    QmrCandidateRecord, RecoveryScoreRecord,
)
from app.recovery.repository import RecoveryRepository


class BuyScoreRepository:
    def __init__(self, db):
        self.db = db

    def eligible(self, evaluation_time, qmr_version, recovery_version, symbols=None, limit=None):
        qmr_rows = RecoveryRepository(self.db).watch_candidates(
            evaluation_time, symbols=symbols, limit=limit, model_version=qmr_version,
        )
        output = []
        for qmr in qmr_rows:
            recovery = self.db.scalar(select(RecoveryScoreRecord).where(
                RecoveryScoreRecord.qmr_candidate_id == qmr.id,
                RecoveryScoreRecord.evaluation_time <= evaluation_time,
                RecoveryScoreRecord.model_version == recovery_version,
            ).order_by(desc(RecoveryScoreRecord.evaluation_time)).limit(1))
            if recovery is not None:
                output.append((qmr, recovery))
        return output

    def previous(self, symbol, evaluation_time, model_version):
        return self.db.scalar(select(BuyScoreRecord).where(
            BuyScoreRecord.symbol == symbol, BuyScoreRecord.evaluation_time < evaluation_time,
            BuyScoreRecord.model_version == model_version,
        ).order_by(desc(BuyScoreRecord.evaluation_time)).limit(1))

    def recovery_signal_price(self, symbol, evaluation_time, recovery_version):
        return self.db.scalar(select(RecoveryScoreRecord.price).where(
            RecoveryScoreRecord.symbol == symbol,
            RecoveryScoreRecord.evaluation_time <= evaluation_time,
            RecoveryScoreRecord.model_version == recovery_version,
            RecoveryScoreRecord.entry_status.in_(("EARLY_ENTRY", "CONFIRMED_ENTRY", "STRONG_ENTRY")),
        ).order_by(RecoveryScoreRecord.evaluation_time).limit(1))

    def feature(self, symbol, interval, name, evaluation_time, max_age=None):
        bare = symbol.upper().removeprefix("US.")
        query = select(FeatureValueRecord).where(
            FeatureValueRecord.symbol.in_((bare, "US." + bare)),
            FeatureValueRecord.interval == interval,
            FeatureValueRecord.feature_name == name,
            FeatureValueRecord.timestamp_utc <= evaluation_time,
            FeatureValueRecord.quality_status == "VALID",
        )
        if max_age is not None:
            query = query.where(FeatureValueRecord.timestamp_utc >= evaluation_time - max_age)
        return self.db.scalar(query.order_by(desc(FeatureValueRecord.timestamp_utc)).limit(1))

    def mapping(self, symbol):
        return list(self.db.scalars(select(InstrumentMapping).where(
            InstrumentMapping.underlying_symbol == symbol.upper(), InstrumentMapping.active.is_(True),
        ).order_by(InstrumentMapping.direction, InstrumentMapping.leveraged_symbol)))

    def sync_mappings(self, definitions):
        created = 0
        for item in definitions:
            existing = self.db.scalar(select(InstrumentMapping).where(
                InstrumentMapping.underlying_symbol == item["underlying_symbol"],
                InstrumentMapping.leveraged_symbol == item["leveraged_symbol"],
                InstrumentMapping.direction == item["direction"],
            ))
            if existing is None:
                self.db.add(InstrumentMapping(**item)); created += 1
            else:
                existing.leverage_multiple = item["leverage_multiple"]
                existing.provider = item["provider"]
                existing.active = item["active"]
        self.db.commit()
        return created

    def save(self, values):
        existing = self.db.scalar(select(BuyScoreRecord).where(
            BuyScoreRecord.symbol == values["symbol"],
            BuyScoreRecord.evaluation_time == values["evaluation_time"],
            BuyScoreRecord.model_version == values["model_version"],
        ))
        if existing:
            return existing, False
        row = BuyScoreRecord(**values)
        self.db.add(row); self.db.commit()
        return row, True

    def rank(self, evaluation_time, model_version):
        confidence_order = case((BuyScoreRecord.data_confidence == "HIGH", 2),
                                (BuyScoreRecord.data_confidence == "MEDIUM", 1), else_=0)
        rows = list(self.db.scalars(select(BuyScoreRecord).where(
            BuyScoreRecord.evaluation_time == evaluation_time,
            BuyScoreRecord.model_version == model_version,
            BuyScoreRecord.buy_status != "REJECT",
        ).order_by(desc(BuyScoreRecord.final_buy_score), desc(BuyScoreRecord.recovery_score),
                   desc(BuyScoreRecord.mispricing_score), desc(BuyScoreRecord.quality_score),
                   desc(confidence_order), BuyScoreRecord.symbol)))
        for current, row in enumerate(rows, 1):
            existing = self.db.scalar(select(BuyRankingRecord).where(
                BuyRankingRecord.buy_score_id == row.id,
            ))
            if existing:
                continue
            previous = self.db.scalar(select(BuyRankingRecord).where(
                BuyRankingRecord.symbol == row.symbol,
                BuyRankingRecord.evaluation_time < evaluation_time,
                BuyRankingRecord.model_version == model_version,
            ).order_by(desc(BuyRankingRecord.evaluation_time)).limit(1))
            previous_rank = None if previous is None else previous.rank_current
            change = None if previous_rank is None else previous_rank - current
            row.rank_current, row.rank_previous, row.rank_change = current, previous_rank, change
            self.db.add(BuyRankingRecord(
                buy_score_id=row.id, symbol=row.symbol, evaluation_time=evaluation_time,
                rank_current=current, rank_previous=previous_rank, rank_change=change,
                final_buy_score=row.final_buy_score, recovery_score=row.recovery_score,
                mispricing_score=row.mispricing_score, quality_score=row.quality_score,
                data_confidence=row.data_confidence, model_version=model_version,
            ))
        self.db.commit()
        return rows

    def latest(self, symbol=None, status=None, grade=None, model_version=None, limit=100, offset=0):
        filters = []
        if model_version: filters.append(BuyScoreRecord.model_version == model_version)
        latest = select(BuyScoreRecord.symbol, func.max(BuyScoreRecord.evaluation_time).label("latest")).where(
            *filters).group_by(BuyScoreRecord.symbol).subquery()
        query = select(BuyScoreRecord).join(latest,
            (BuyScoreRecord.symbol == latest.c.symbol) & (BuyScoreRecord.evaluation_time == latest.c.latest))
        if model_version: query = query.where(BuyScoreRecord.model_version == model_version)
        if symbol: query = query.where(BuyScoreRecord.symbol == symbol.upper())
        if status: query = query.where(BuyScoreRecord.buy_status == status.upper())
        if grade: query = query.where(BuyScoreRecord.buy_grade == grade.upper())
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        confidence_order = case((BuyScoreRecord.data_confidence == "HIGH", 2),
                                (BuyScoreRecord.data_confidence == "MEDIUM", 1), else_=0)
        rows = list(self.db.scalars(query.order_by(desc(BuyScoreRecord.final_buy_score),
            desc(BuyScoreRecord.recovery_score), desc(BuyScoreRecord.mispricing_score),
            desc(BuyScoreRecord.quality_score), desc(confidence_order), BuyScoreRecord.symbol).offset(offset).limit(limit)))
        return rows, total

    def history(self, symbol, model_version, limit=100):
        return list(self.db.scalars(select(BuyScoreRecord).where(
            BuyScoreRecord.symbol == symbol.upper(), BuyScoreRecord.model_version == model_version,
        ).order_by(desc(BuyScoreRecord.evaluation_time)).limit(limit)))

    def rankings(self, model_version, limit=20, offset=0):
        latest_time = self.db.scalar(select(func.max(BuyRankingRecord.evaluation_time)).where(
            BuyRankingRecord.model_version == model_version))
        if latest_time is None:
            return [], 0
        query = select(BuyRankingRecord).where(
            BuyRankingRecord.model_version == model_version,
            BuyRankingRecord.evaluation_time == latest_time,
        )
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        return list(self.db.scalars(query.order_by(BuyRankingRecord.rank_current).offset(offset).limit(limit))), total

    def latest_evaluation_time(self):
        return self.db.scalar(select(func.max(BuyScoreRecord.evaluation_time)))
