import base64
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.research.service import ResearchService

router = APIRouter(
    prefix="/api/research", tags=["研究中心"],
)


class NoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    note_type: str = "OBSERVATION"
    created_by: Optional[str] = None


class AttachmentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str
    uploaded_by: Optional[str] = None


class InvestigationPatch(BaseModel):
    status: str
    result: Optional[dict] = None
    approved_by: Optional[str] = None


@router.get("", dependencies=[Depends(require_read)])
def list_research(
    symbol: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    service = ResearchService(db)
    rows = service.list(symbol=symbol, limit=limit, offset=offset)
    return {
        "items": [_workspace(row) for row in rows],
        "total": service.count(symbol), "limit": limit, "offset": offset,
    }


@router.get("/{workspace_id}", dependencies=[Depends(require_read)])
def detail(workspace_id: int, db: Session = Depends(get_db)):
    try:
        value = ResearchService(db).detail(workspace_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return _detail(value)


@router.get("/{workspace_id}/timeline", dependencies=[Depends(require_read)])
def timeline(workspace_id: int, db: Session = Depends(get_db)):
    try:
        rows = ResearchService(db).timeline(workspace_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return {"items": [_row(row) for row in rows], "total": len(rows)}


@router.post("/{workspace_id}/notes", dependencies=[Depends(require_admin)])
def add_note(workspace_id: int, payload: NoteRequest, db: Session = Depends(get_db)):
    try:
        return _row(ResearchService(db).add_note(
            workspace_id, payload.content, payload.note_type, payload.created_by,
        ))
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{workspace_id}/attachments", dependencies=[Depends(require_admin)])
def add_attachment(
    workspace_id: int, payload: AttachmentRequest, db: Session = Depends(get_db),
):
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
        return _row(ResearchService(db).add_attachment(
            workspace_id, payload.filename, content, payload.uploaded_by,
        ))
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/{workspace_id}/similarity", dependencies=[Depends(require_read)])
def similarity(
    workspace_id: int, limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    try:
        rows = ResearchService(db).similarity(workspace_id, limit)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return {"items": rows, "total": len(rows)}


@router.get("/{workspace_id}/investigations", dependencies=[Depends(require_read)])
def investigations(
    workspace_id: int, status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        rows = ResearchService(db).investigations(workspace_id, status)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return {"items": [_row(row) for row in rows], "total": len(rows)}


@router.patch("/investigations/{investigation_id}", dependencies=[Depends(require_admin)])
def update_investigation(
    investigation_id: int, payload: InvestigationPatch,
    db: Session = Depends(get_db),
):
    try:
        return _row(ResearchService(db).update_investigation(
            investigation_id, payload.status, payload.result, payload.approved_by,
        ))
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _workspace(row):
    return _row(row)


def _row(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _detail(value):
    return {
        "workspace": _row(value["workspace"]),
        "opportunity": _row(value["opportunity"]),
        "review": _row(value["review"]) if value["review"] else None,
        "ai_reviews": [_row(row) for row in value["ai_reviews"]],
        "timeline": [_row(row) for row in value["timeline"]],
        "evidence": [_row(row) for row in value["evidence"]],
        "notes": [_row(row) for row in value["notes"]],
        "attachments": [_row(row) for row in value["attachments"]],
        "investigations": [_row(row) for row in value["investigations"]],
    }
