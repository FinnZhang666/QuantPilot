from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.companion.service import CompanionService
from app.database.session import get_db
from app.dashboard.auth import require_admin, require_read

router = APIRouter(
    prefix="/api/companion-analyses", tags=["AI Companion"],
    dependencies=[Depends(require_read)],
)
alias_router = APIRouter(
    prefix="/api/ai-companion", tags=["AI Companion"],
    dependencies=[Depends(require_read)],
)
internal_router = APIRouter(
    prefix="/internal/companion", tags=["Internal AI Companion"],
    dependencies=[Depends(require_admin)],
)


class GenerateCompanionRequest(BaseModel):
    language: Optional[str] = None
    provider: Optional[str] = None
    force: bool = False
    dry_run: bool = True


class UnifiedGenerateCompanionRequest(GenerateCompanionRequest):
    object_type: str
    object_id: Optional[str] = None


@router.get("")
def list_analyses(
    context_type: Optional[str] = None, trade_plan_id: Optional[int] = None,
    user_position_id: Optional[int] = None, trade_review_id: Optional[int] = None,
    status: Optional[str] = None, language: Optional[str] = None,
    provider: Optional[str] = None, start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None, limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0), db=Depends(get_db),
):
    service = CompanionService(db)
    filters = {
        "context_type": context_type, "trade_plan_id": trade_plan_id,
        "user_position_id": user_position_id, "trade_review_id": trade_review_id,
        "status": status, "language": language, "provider": provider,
        "start_time": start_time, "end_time": end_time,
        "limit": limit, "offset": offset,
    }
    rows = service.list(**filters)
    return {
        "items": [_serialize(row, service.source_summary(row)) for row in rows],
        "total": service.count(**filters), "limit": limit, "offset": offset,
    }


@router.get("/{analysis_id}")
def get_analysis(analysis_id: int, db=Depends(get_db)):
    service = CompanionService(db)
    row = service.get(analysis_id)
    if row is None:
        raise HTTPException(404, "AI Companion Analysis不存在。")
    return _serialize(row, service.source_summary(row))


@alias_router.get("/outputs")
def list_outputs(
    context_type: Optional[str] = None, status: Optional[str] = None,
    provider: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0), db=Depends(get_db),
):
    service = CompanionService(db)
    filters = {
        "context_type": context_type, "status": status, "provider": provider,
        "limit": limit, "offset": offset,
    }
    rows = service.list(**filters)
    return {"items": [_serialize(row, service.source_summary(row)) for row in rows],
            "total": service.count(**filters), "limit": limit, "offset": offset}


@alias_router.get("/outputs/{analysis_id}")
def get_output(analysis_id: int, db=Depends(get_db)):
    return get_analysis(analysis_id, db)


@internal_router.post("/trade-plans/{plan_id}/generate", include_in_schema=False)
def generate_plan(plan_id: str, request: GenerateCompanionRequest, db=Depends(get_db)):
    return _generate(CompanionService(db).generate_trade_plan_analysis, plan_id, request)


@internal_router.post("/positions/{position_id}/generate", include_in_schema=False)
def generate_position(position_id: int, request: GenerateCompanionRequest, db=Depends(get_db)):
    return _generate(CompanionService(db).generate_position_analysis, position_id, request)


@internal_router.post("/reviews/{review_id}/generate", include_in_schema=False)
def generate_review(review_id: int, request: GenerateCompanionRequest, db=Depends(get_db)):
    return _generate(CompanionService(db).generate_review_analysis, review_id, request)


def _generate(method, object_id, request):
    try:
        result = method(object_id, **request.model_dump())
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if result.get("analysis") is not None:
        result = {**result, "analysis": _serialize(result["analysis"])}
    return result


def _serialize(row, source=None):
    return {
        "id": row.id, "analysis_key": row.analysis_key,
        "input_hash": row.input_hash,
        "context_type": row.context_type, "trade_plan_id": row.trade_plan_id,
        "user_position_id": row.user_position_id, "trade_review_id": row.trade_review_id,
        "language": row.language, "template_id": row.template_id,
        "template_version": row.template_version,
        "context_schema_version": row.context_schema_version,
        "response_schema_version": row.response_schema_version,
        "provider": row.provider, "model": row.model, "status": row.status,
        "summary": row.summary, "structured_response": row.structured_response_json,
        "source": source or {},
        "source_references": {
            "trade_plan_id": row.trade_plan_id,
            "user_position_id": row.user_position_id,
            "trade_review_id": row.trade_review_id,
        },
        "error_code": row.error_code, "error_summary": row.error_summary,
        "request_started_at": row.request_started_at,
        "request_completed_at": row.request_completed_at,
        "token_input": row.token_input, "token_output": row.token_output,
        "latency_ms": row.latency_ms,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


unified_internal_router = APIRouter(
    prefix="/internal/ai-companion", tags=["Internal AI Companion"],
    dependencies=[Depends(require_admin)],
)


@unified_internal_router.post("/generate", include_in_schema=False)
def generate_unified(request: UnifiedGenerateCompanionRequest, db=Depends(get_db)):
    service = CompanionService(db)
    object_type = request.object_type.upper()
    options = request.model_dump(exclude={"object_type", "object_id"})
    if object_type == "STATISTICS":
        clean_request = GenerateCompanionRequest(**options)
        return _generate(
            lambda _, **kwargs: service.generate_statistics_analysis(**kwargs),
            "global", clean_request,
        )
    if request.object_id is None:
        raise HTTPException(422, "该Companion场景必须提供object_id。")
    methods = {
        "TRADE_PLAN": service.generate_trade_plan_analysis,
        "USER_POSITION": service.generate_position_analysis,
        "TRADE_REVIEW": service.generate_review_analysis,
    }
    method = methods.get(object_type)
    if method is None:
        raise HTTPException(422, "object_type必须是TRADE_PLAN、USER_POSITION、TRADE_REVIEW或STATISTICS。")
    try:
        object_id = request.object_id if object_type == "TRADE_PLAN" else int(request.object_id)
    except ValueError:
        raise HTTPException(422, "object_id格式无效。")
    try:
        result = method(object_id, **options)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if result.get("analysis") is not None:
        result = {**result, "analysis": _serialize(result["analysis"])}
    return result
