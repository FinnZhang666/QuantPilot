import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy import desc, func, select

from app.database.models import (
    AIReviewAnalysis, CandidatePoolEntry, DevelopmentIssue, Notification,
    Opportunity, OpportunityReview, ResearchAttachment, ResearchEvidence,
    ResearchInvestigation, ResearchNote, ResearchTimelineEvent, ResearchWorkspace,
)
from app.research.similarity import similarity_score

INVESTIGATION_STATUSES = {"NEW", "OPEN", "TESTING", "VERIFIED", "REJECTED", "CLOSED"}
NOTE_TYPES = {"OBSERVATION", "HYPOTHESIS", "VALIDATION", "EXPERIENCE", "NEXT_STEP"}
ALLOWED_ATTACHMENTS = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".csv": "text/csv", ".json": "application/json",
    ".md": "text/markdown", ".markdown": "text/markdown",
}


class ResearchService:
    def __init__(self, db, attachment_root="data/research_attachments"):
        self.db = db
        self.attachment_root = Path(attachment_root)

    def ensure_workspace(self, opportunity_id: int):
        opportunity = self.db.get(Opportunity, opportunity_id)
        if opportunity is None:
            raise KeyError("Opportunity不存在。")
        row = self.db.scalar(select(ResearchWorkspace).where(
            ResearchWorkspace.opportunity_id == opportunity_id,
        ))
        if row is None:
            row = ResearchWorkspace(
                opportunity_id=opportunity.id, symbol=opportunity.symbol,
                timeframe=opportunity.timeframe, strategy_name=opportunity.strategy_name,
                status="ACTIVE", summary_json={
                    "direction": opportunity.direction, "score": opportunity.score,
                    "confidence": opportunity.confidence,
                },
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                row, "OPPORTUNITY_GENERATED", "Opportunity Generated",
                "OPPORTUNITY", str(opportunity.id), opportunity.detected_at,
                {"status": opportunity.status, "score": opportunity.score},
            )
            self.db.commit()
        self.sync(row.id)
        return row

    def sync_all(self, limit=500):
        ids = list(self.db.scalars(select(Opportunity.id).order_by(
            desc(Opportunity.detected_at),
        ).limit(limit)))
        return [self.ensure_workspace(value) for value in ids]

    def sync(self, workspace_id: int):
        workspace = self.get(workspace_id)
        opportunity = self.db.get(Opportunity, workspace.opportunity_id)
        self._event(
            workspace, "OPPORTUNITY_STATUS", "Opportunity " + opportunity.status,
            "OPPORTUNITY_STATUS", "%s:%s" % (opportunity.id, opportunity.status),
            opportunity.updated_at, {"status": opportunity.status},
        )
        if opportunity.candidate_pool_entry_id:
            candidate = self.db.get(CandidatePoolEntry, opportunity.candidate_pool_entry_id)
            if candidate:
                self._event(
                    workspace, "CANDIDATE_CREATED", "Candidate Created",
                    "CANDIDATE", str(candidate.id), candidate.first_seen_at,
                    {"direction": candidate.direction, "score": candidate.final_score},
                )
        if opportunity.notification_status == "SENT":
            self._event(
                workspace, "TELEGRAM_SENT", "Telegram Sent",
                "NOTIFICATION", opportunity.notification_message_id or str(opportunity.id),
                opportunity.updated_at, {"status": opportunity.notification_status},
            )
        review = self.db.scalar(select(OpportunityReview).where(
            OpportunityReview.opportunity_id == opportunity.id,
        ))
        if review:
            self._event(
                workspace, "REVIEW_COMPLETED", "Review Completed",
                "REVIEW", str(review.id), review.review_time,
                {"return_percent": str(review.return_percent), "mfe": str(review.mfe_percent),
                 "mae": str(review.mae_percent), "status": review.review_status},
            )
            self._review_evidence(workspace, review)
        analyses = list(self.db.scalars(select(AIReviewAnalysis).where(
            AIReviewAnalysis.opportunity_id == opportunity.id,
        )))
        for analysis in analyses:
            self._event(
                workspace, "AI_REVIEW", "AI Review",
                "AI_REVIEW", str(analysis.id), analysis.completed_at or analysis.created_at,
                {"status": analysis.status, "confidence": analysis.confidence_score},
            )
            ai_evidence = self._ai_evidence(workspace, analysis)
            self.db.flush()
            self._sync_investigations(workspace, analysis, ai_evidence.id)
        self._snapshot_evidence(workspace, opportunity)
        self.db.commit()
        return workspace

    def list(self, symbol=None, limit=100, offset=0):
        query = select(ResearchWorkspace)
        if symbol:
            query = query.where(ResearchWorkspace.symbol == _symbol(symbol))
        return list(self.db.scalars(query.order_by(
            desc(ResearchWorkspace.updated_at),
        ).offset(offset).limit(limit)))

    def count(self, symbol=None):
        query = select(func.count()).select_from(ResearchWorkspace)
        if symbol:
            query = query.where(ResearchWorkspace.symbol == _symbol(symbol))
        return self.db.scalar(query) or 0

    def get(self, workspace_id):
        row = self.db.get(ResearchWorkspace, workspace_id)
        if row is None:
            raise KeyError("Research Workspace不存在。")
        return row

    def detail(self, workspace_id):
        workspace = self.sync(workspace_id)
        opportunity = self.db.get(Opportunity, workspace.opportunity_id)
        review = self.db.scalar(select(OpportunityReview).where(
            OpportunityReview.opportunity_id == opportunity.id,
        ))
        analyses = list(self.db.scalars(select(AIReviewAnalysis).where(
            AIReviewAnalysis.opportunity_id == opportunity.id,
        ).order_by(desc(AIReviewAnalysis.created_at))))
        return {
            "workspace": workspace, "opportunity": opportunity, "review": review,
            "ai_reviews": analyses,
            "timeline": self.timeline(workspace_id),
            "evidence": self.evidence(workspace_id),
            "notes": self.notes(workspace_id),
            "attachments": self.attachments(workspace_id),
            "investigations": self.investigations(workspace_id),
        }

    def timeline(self, workspace_id):
        self.get(workspace_id)
        return list(self.db.scalars(select(ResearchTimelineEvent).where(
            ResearchTimelineEvent.workspace_id == workspace_id,
        ).order_by(ResearchTimelineEvent.event_time, ResearchTimelineEvent.id)))

    def evidence(self, workspace_id):
        return list(self.db.scalars(select(ResearchEvidence).where(
            ResearchEvidence.workspace_id == workspace_id,
        ).order_by(ResearchEvidence.id)))

    def add_note(self, workspace_id, content, note_type="OBSERVATION", created_by=None):
        workspace = self.get(workspace_id)
        kind = note_type.upper()
        if kind not in NOTE_TYPES:
            raise ValueError("Research Note类型无效。")
        if not content or not content.strip():
            raise ValueError("Research Note不能为空。")
        row = ResearchNote(
            workspace_id=workspace.id, note_type=kind,
            content=content.strip(), created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()
        self._event(
            workspace, "MANUAL_NOTE", "Manual Note", "NOTE", str(row.id),
            row.created_at, {"note_type": kind},
        )
        self.db.commit()
        return row

    def notes(self, workspace_id):
        return list(self.db.scalars(select(ResearchNote).where(
            ResearchNote.workspace_id == workspace_id,
        ).order_by(desc(ResearchNote.created_at))))

    def add_attachment(self, workspace_id, filename, content, uploaded_by=None):
        workspace = self.get(workspace_id)
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_ATTACHMENTS:
            raise ValueError("附件仅支持PNG、JPG、CSV、JSON和Markdown。")
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("附件不能超过10MB。")
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)
        stored = "%s-%s" % (uuid4().hex, safe_name)
        directory = self.attachment_root / str(workspace.id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / stored
        target.write_bytes(content)
        row = ResearchAttachment(
            workspace_id=workspace.id, original_name=Path(filename).name,
            stored_name=stored, media_type=ALLOWED_ATTACHMENTS[suffix],
            size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
            storage_path=str(target), uploaded_by=uploaded_by,
        )
        self.db.add(row)
        self.db.flush()
        self._event(
            workspace, "ATTACHMENT_ADDED", "Attachment Added",
            "ATTACHMENT", str(row.id), row.created_at,
            {"name": row.original_name, "media_type": row.media_type},
        )
        self.db.commit()
        return row

    def attachments(self, workspace_id):
        return list(self.db.scalars(select(ResearchAttachment).where(
            ResearchAttachment.workspace_id == workspace_id,
        ).order_by(desc(ResearchAttachment.created_at))))

    def investigations(self, workspace_id, status=None):
        query = select(ResearchInvestigation).where(
            ResearchInvestigation.workspace_id == workspace_id,
        )
        if status:
            query = query.where(ResearchInvestigation.status == status.upper())
        return list(self.db.scalars(query.order_by(
            desc(ResearchInvestigation.created_at),
        )))

    def update_investigation(self, investigation_id, status, result=None, approved_by=None):
        row = self.db.get(ResearchInvestigation, investigation_id)
        if row is None:
            raise KeyError("Investigation不存在。")
        target = status.upper()
        if target not in INVESTIGATION_STATUSES:
            raise ValueError("Investigation状态无效。")
        row.status = target
        if result is not None:
            row.result_json = result
        if approved_by is not None:
            row.approved_by = approved_by
        workspace = self.get(row.workspace_id)
        self._event(
            workspace, "INVESTIGATION_UPDATED", "Investigation " + target,
            "INVESTIGATION_STATUS", "%s:%s" % (row.id, target),
            datetime.now(timezone.utc), {"status": target},
        )
        self.db.commit()
        return row

    def similarity(self, workspace_id, limit=10):
        workspace = self.get(workspace_id)
        current = self.db.get(Opportunity, workspace.opportunity_id)
        current_review = self.db.scalar(select(OpportunityReview).where(
            OpportunityReview.opportunity_id == current.id,
        ))
        rows = list(self.db.scalars(select(Opportunity).where(
            Opportunity.id != current.id,
        )))
        output = []
        for opportunity in rows:
            review = self.db.scalar(select(OpportunityReview).where(
                OpportunityReview.opportunity_id == opportunity.id,
            ))
            score = similarity_score(current, opportunity, current_review, review)
            output.append({
                "opportunity_id": opportunity.id, "symbol": opportunity.symbol,
                "timeframe": opportunity.timeframe, "direction": opportunity.direction,
                "strategy": opportunity.strategy_name, "market_regime": opportunity.market_regime,
                "similarity": score,
                "return_percent": str(review.return_percent) if review and review.return_percent is not None else None,
            })
        return sorted(output, key=lambda row: (-row["similarity"], row["opportunity_id"]))[:limit]

    def _event(self, workspace, event_type, title, source_type, source_id, event_time, metadata):
        existing = self.db.scalar(select(ResearchTimelineEvent).where(
            ResearchTimelineEvent.workspace_id == workspace.id,
            ResearchTimelineEvent.event_type == event_type,
            ResearchTimelineEvent.source_type == source_type,
            ResearchTimelineEvent.source_id == source_id,
        ))
        if existing:
            return existing
        row = ResearchTimelineEvent(
            workspace_id=workspace.id, event_type=event_type,
            event_time=event_time or datetime.now(timezone.utc),
            title=title, source_type=source_type, source_id=source_id,
            metadata_json=metadata or {},
        )
        self.db.add(row)
        return row

    def _put_evidence(self, workspace, kind, label, source_type, source_id, value, observed_at=None):
        existing = self.db.scalar(select(ResearchEvidence).where(
            ResearchEvidence.workspace_id == workspace.id,
            ResearchEvidence.evidence_type == kind,
            ResearchEvidence.source_type == source_type,
            ResearchEvidence.source_id == str(source_id),
            ResearchEvidence.label == label,
        ))
        if existing:
            existing.value_json = value
            return existing
        row = ResearchEvidence(
            workspace_id=workspace.id, evidence_type=kind, label=label,
            source_type=source_type, source_id=str(source_id),
            value_json=value, observed_at=observed_at,
        )
        self.db.add(row)
        return row

    def _snapshot_evidence(self, workspace, opportunity):
        snapshots = {
            "FEATURE": opportunity.feature_snapshot_json or {},
            "STRATEGY": opportunity.strategy_snapshot_json or {},
            "DECISION": opportunity.decision_snapshot_json or {},
            "MARKET_REGIME": {"regime": opportunity.market_regime},
        }
        for kind, value in snapshots.items():
            self._put_evidence(
                workspace, kind, kind.title(), "OPPORTUNITY", opportunity.id,
                value, opportunity.bar_time,
            )

    def _review_evidence(self, workspace, review):
        for label, value in (
            ("Return", review.return_percent), ("MFE", review.mfe_percent),
            ("MAE", review.mae_percent), ("Price Path", review.price_path_json),
        ):
            payload = value if label == "Price Path" else {
                "value": str(value) if value is not None else None,
            }
            self._put_evidence(
                workspace, "OUTCOME", label, "REVIEW", review.id,
                {"items": payload} if isinstance(payload, list) else payload,
                review.review_time,
            )

    def _ai_evidence(self, workspace, analysis):
        return self._put_evidence(
            workspace, "AI_CONCLUSION", "AI Review Conclusion", "AI_REVIEW", analysis.id,
            {"summary": analysis.summary, "confidence": analysis.confidence_score,
             "positive": analysis.positive_factors_json, "negative": analysis.negative_factors_json,
             "risks": analysis.risk_factors_json},
            analysis.completed_at,
        )

    def _sync_investigations(self, workspace, analysis, evidence_id):
        for index, item in enumerate(analysis.investigation_items_json or []):
            source_id = "%s:%s" % (analysis.id, index)
            existing = self.db.scalar(select(ResearchInvestigation).where(
                ResearchInvestigation.workspace_id == workspace.id,
                ResearchInvestigation.source_type == "AI_REVIEW",
                ResearchInvestigation.source_id == source_id,
            ))
            if existing:
                continue
            row = ResearchInvestigation(
                workspace_id=workspace.id,
                title=item.get("title") or "AI Investigation",
                description=item.get("description") or item.get("question"),
                status="NEW", priority=item.get("priority", "MEDIUM").upper(),
                source_type="AI_REVIEW", source_id=source_id,
                evidence_ids_json=[evidence_id], result_json={},
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                workspace, "INVESTIGATION_CREATED", "Investigation Created",
                "INVESTIGATION", str(row.id), row.created_at,
                {"priority": row.priority, "title": row.title},
            )


def _symbol(value):
    return value.upper().replace("US.", "")
