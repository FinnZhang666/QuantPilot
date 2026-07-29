from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dashboard.auth import require_admin, require_read
from app.database.models import DevelopmentIssue
from app.database.session import get_db

router = APIRouter(prefix="/api/development/issues", tags=["开发看板"])
SOURCES = {"CEO", "ADMIN", "AI", "USER_FEEDBACK", "SYSTEM"}
STATUSES = {
    "INBOX", "INVESTIGATING", "EVIDENCE_READY", "WAITING_APPROVAL", "APPROVED",
    "CODEX_PROMPT_READY", "IN_DEVELOPMENT", "REVIEW", "COMPLETED", "REJECTED",
}
PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    source_type: str = "ADMIN"
    source_reference: Optional[str] = None
    category: str = "GENERAL"
    priority: str = "MEDIUM"
    evidence_json: Optional[dict] = None
    created_by: Optional[str] = None


class IssuePatch(BaseModel):
    status: str
    approved_by: Optional[str] = None


@router.get("", dependencies=[Depends(require_read)])
def list_issues(
    status: Optional[str] = None, source_type: Optional[str] = None,
    priority: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    filters = []
    if status:
        filters.append(DevelopmentIssue.status == status.upper())
    if source_type:
        filters.append(DevelopmentIssue.source_type == source_type.upper())
    if priority:
        filters.append(DevelopmentIssue.priority == priority.upper())
    total = db.scalar(select(func.count()).select_from(DevelopmentIssue).where(*filters)) or 0
    rows = db.scalars(select(DevelopmentIssue).where(*filters).order_by(
        DevelopmentIssue.created_at.desc(),
    ).offset(offset).limit(limit))
    return {"items": [_issue(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/{issue_id}", dependencies=[Depends(require_read)])
def get_issue(issue_id: int, db: Session = Depends(get_db)):
    row = db.get(DevelopmentIssue, issue_id)
    if row is None:
        raise HTTPException(404, "开发Issue不存在。")
    return _issue(row)


@router.post("", dependencies=[Depends(require_admin)])
def create_issue(payload: IssueCreate, db: Session = Depends(get_db)):
    source = payload.source_type.upper()
    priority = payload.priority.upper()
    if source not in SOURCES:
        raise HTTPException(400, "Issue来源类型无效。")
    if priority not in PRIORITIES:
        raise HTTPException(400, "Issue优先级无效。")
    row = DevelopmentIssue(
        title=payload.title, description=payload.description, source_type=source,
        source_reference=payload.source_reference, category=payload.category.upper(),
        priority=priority, status="INBOX", evidence_json=payload.evidence_json,
        created_by=payload.created_by,
    )
    db.add(row)
    db.commit()
    return _issue(row)


@router.patch("/{issue_id}", dependencies=[Depends(require_admin)])
def update_issue(issue_id: int, payload: IssuePatch, db: Session = Depends(get_db)):
    row = db.get(DevelopmentIssue, issue_id)
    if row is None:
        raise HTTPException(404, "开发Issue不存在。")
    status = payload.status.upper()
    if status not in STATUSES:
        raise HTTPException(400, "Issue状态无效。")
    row.status = status
    if payload.approved_by is not None:
        row.approved_by = payload.approved_by
    db.commit()
    return _issue(row)


def _issue(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
