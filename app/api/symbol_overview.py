from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.market_snapshot.service import SnapshotNotFound
from app.symbol_overview.service import SymbolOverviewService


router = APIRouter(
    prefix="/api/symbols", tags=["Symbol Overview"],
    dependencies=[Depends(require_read)],
)
internal_router = APIRouter(
    prefix="/internal/symbols", tags=["Internal Symbol Overview"],
    dependencies=[Depends(require_admin)],
)


class AIEntryRequest(BaseModel):
    market: str = "US"
    language: Optional[str] = None
    provider: Optional[str] = None
    force: bool = False
    dry_run: bool = True


@router.get("/{symbol}/overview")
def symbol_overview(symbol: str, market: str = "US", db=Depends(get_db)):
    try:
        value = SymbolOverviewService(db).get(symbol, market)
        return SymbolOverviewService.serialize(value)
    except SnapshotNotFound as exc:
        raise HTTPException(404, str(exc))


@internal_router.post("/{symbol}/ai-analysis", include_in_schema=False)
def symbol_ai_entry(symbol: str, request: AIEntryRequest, db=Depends(get_db)):
    options = request.model_dump(exclude={"market"})
    try:
        result = SymbolOverviewService(db).ai_entry(symbol, request.market, **options)
    except SnapshotNotFound as exc:
        raise HTTPException(404, str(exc))
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc).strip("'"))
    analysis = result.get("analysis")
    if analysis is not None:
        result["analysis"] = {
            "id": analysis.id, "status": analysis.status,
            "summary": analysis.summary, "context_type": analysis.context_type,
        }
    return result
