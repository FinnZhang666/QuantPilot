from sqlalchemy import and_, desc, exists, func, or_, select

from app.database.models import (
    MarketBar, MispricingScoreRecord, QmrCandidateRecord, QualityScoreRecord,
    UniverseInstrument, UniverseMembership, InstrumentMapping,
)


class QmrRepository:
    def __init__(self, db):
        self.db = db

    def active_universe(self, evaluation_time, symbols=None):
        query = select(UniverseInstrument).where(
            UniverseInstrument.first_seen <= evaluation_time,
            exists(select(UniverseMembership.id).where(
                UniverseMembership.universe_id == UniverseInstrument.id,
                UniverseMembership.first_seen <= evaluation_time,
                or_(UniverseMembership.is_active.is_(True), UniverseMembership.last_seen >= evaluation_time),
            )),
        )
        if symbols:
            query = query.where(UniverseInstrument.symbol.in_(symbols))
        return list(self.db.scalars(query.order_by(UniverseInstrument.symbol)))

    def memberships(self, universe_id, evaluation_time):
        return list(self.db.scalars(select(UniverseMembership).where(
            UniverseMembership.universe_id == universe_id,
            UniverseMembership.first_seen <= evaluation_time,
            or_(UniverseMembership.is_active.is_(True), UniverseMembership.last_seen >= evaluation_time),
        )))

    def bars(self, symbol, evaluation_time, limit=1300):
        bare = symbol.upper().removeprefix("US.")
        rows = list(self.db.scalars(select(MarketBar).where(
            MarketBar.symbol.in_((bare, "US." + bare)), MarketBar.interval == "1d",
            MarketBar.timestamp_utc <= evaluation_time, MarketBar.is_blank.is_(False),
        ).order_by(desc(MarketBar.timestamp_utc)).limit(limit)))
        deduplicated = {}
        for row in reversed(rows):
            deduplicated[row.timestamp_utc] = row
        return [deduplicated[key] for key in sorted(deduplicated)]

    def fundamental_symbol(self, symbol):
        mapping = self.db.scalar(select(InstrumentMapping).where(
            InstrumentMapping.leveraged_symbol == symbol.upper(),
            InstrumentMapping.active.is_(True),
        ).order_by(InstrumentMapping.id).limit(1))
        return mapping.underlying_symbol if mapping else symbol.upper()

    def save(self, universe, evaluation_time, quality, quality_components, coverage,
             mispricing, mispricing_components, event, sources, confidence, model_version,
             thresholds):
        existing = self.db.scalar(select(QmrCandidateRecord).where(
            QmrCandidateRecord.symbol == universe.symbol,
            QmrCandidateRecord.evaluation_time == evaluation_time,
            QmrCandidateRecord.model_version == model_version,
        ))
        if existing:
            return existing, False
        q = QualityScoreRecord(
            universe_id=universe.id, symbol=universe.symbol, evaluation_time=evaluation_time,
            quality_score=quality, score_components_json=quality_components,
            data_sources_json=sources, data_confidence=confidence, data_coverage=coverage,
            model_version=model_version,
        )
        m = MispricingScoreRecord(
            universe_id=universe.id, symbol=universe.symbol, evaluation_time=evaluation_time,
            mispricing_score=mispricing, fundamental_risk=event.fundamental_risk,
            event_risk=event.event_risk, news_confidence=event.confidence,
            score_components_json=mispricing_components, data_sources_json=sources,
            data_confidence=confidence, model_version=model_version,
        )
        self.db.add_all([q, m]); self.db.flush()
        if event.fundamental_risk == "HIGH" or quality < thresholds["quality_min"] or coverage < thresholds["minimum_quality_coverage"]:
            status = "REJECT"
        elif mispricing >= thresholds["mispricing_min"]:
            status = "WATCH"
        else:
            status = "NO_SIGNAL"
        candidate = QmrCandidateRecord(
            universe_id=universe.id, quality_score_id=q.id, mispricing_score_id=m.id,
            symbol=universe.symbol, evaluation_time=evaluation_time,
            quality_score=quality, mispricing_score=mispricing,
            combined_score=round((quality + mispricing) / 2),
            fundamental_risk=event.fundamental_risk, event_risk=event.event_risk,
            candidate_status=status,
            score_components_json={"quality": quality_components, "mispricing": mispricing_components},
            data_sources_json=sources, data_confidence=confidence, model_version=model_version,
        )
        self.db.add(candidate); self.db.commit()
        return candidate, True

    def list_candidates(self, status=None, symbol=None, sort="combined", limit=100, offset=0):
        filters = []
        if status: filters.append(QmrCandidateRecord.candidate_status == status.upper())
        if symbol: filters.append(QmrCandidateRecord.symbol == symbol.upper())
        # One current record per symbol; history remains available through detail.
        latest = select(
            QmrCandidateRecord.symbol,
            func.max(QmrCandidateRecord.evaluation_time).label("latest"),
        ).group_by(QmrCandidateRecord.symbol).subquery()
        query = select(QmrCandidateRecord).join(latest,
            (QmrCandidateRecord.symbol == latest.c.symbol) &
            (QmrCandidateRecord.evaluation_time == latest.c.latest)).where(*filters)
        order = {"quality": QmrCandidateRecord.quality_score,
                 "mispricing": QmrCandidateRecord.mispricing_score,
                 "combined": QmrCandidateRecord.combined_score}.get(sort, QmrCandidateRecord.combined_score)
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        return list(self.db.scalars(query.order_by(order.desc(), QmrCandidateRecord.symbol).offset(offset).limit(limit))), total

    def history(self, symbol, limit=100):
        return list(self.db.scalars(select(QmrCandidateRecord).where(
            QmrCandidateRecord.symbol == symbol.upper(),
        ).order_by(desc(QmrCandidateRecord.evaluation_time)).limit(limit)))

    def latest_evaluation_time(self):
        return self.db.scalar(select(func.max(QmrCandidateRecord.evaluation_time)))
