from typing import Optional

from sqlalchemy import desc, select

from app.database.models import AIReviewAnalysis


class AIReviewRepository:
    def __init__(self, db):
        self.db = db

    def get(self, analysis_id: int) -> Optional[AIReviewAnalysis]:
        return self.db.get(AIReviewAnalysis, analysis_id)

    def find_identity(self, review_id, version, provider, model, input_hash):
        return self.db.scalar(select(AIReviewAnalysis).where(
            AIReviewAnalysis.opportunity_review_id == review_id,
            AIReviewAnalysis.analysis_version == version,
            AIReviewAnalysis.provider == provider,
            AIReviewAnalysis.model == model,
            AIReviewAnalysis.input_hash == input_hash,
        ))

    def recent(self, limit=100):
        return list(self.db.scalars(select(AIReviewAnalysis).order_by(
            desc(AIReviewAnalysis.created_at),
        ).limit(limit)))
