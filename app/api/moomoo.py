from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.data.providers.moomoo import MoomooCapabilityReport, MoomooConnectionManager
from app.database.models import MoomooConnectionCheck, SystemEvent
from app.database.session import get_db

router = APIRouter(prefix="/moomoo", tags=["Moomoo"])


class CheckRequest(BaseModel):
    symbols: List[str] = Field(default_factory=lambda: ["US.QQQ", "US.SOXL"], max_length=10)


def _manager(settings: Settings) -> MoomooConnectionManager:
    return MoomooConnectionManager(
        settings.moomoo_opend_host,
        settings.moomoo_opend_port,
        settings.moomoo_connection_timeout_seconds,
    )


def _save_report(db: Session, report: MoomooCapabilityReport) -> None:
    db.add(
        MoomooConnectionCheck(
            opend_reachable=report.opend_reachable,
            opend_logged_in=report.opend_logged_in,
            sdk_version=report.sdk_version,
            opend_version=report.opend_version,
            quote_capabilities_json={
                "quote_context_available": report.quote_context_available,
                "us_quote_available": report.us_quote_available,
                "snapshot_available": report.snapshot_available,
                "historical_kline_available": report.historical_kline_available,
                "market_state_available": report.market_state_available,
                "symbol_results": report.symbol_results,
            },
            paper_account_found=report.paper_account_found,
            live_account_found=report.live_account_found,
            errors_json=report.errors,
            warnings_json=report.warnings,
            status_code=report.status_code,
            status_message_zh=report.status_message_zh,
        )
    )
    level = "INFO" if not report.errors else "WARNING"
    db.add(
        SystemEvent(
            level=level,
            component="moomoo",
            event_type="capability_check",
            message=report.status_message_zh,
            payload_json={
                "status_code": report.status_code,
                "opend_reachable": report.opend_reachable,
                "opend_logged_in": report.opend_logged_in,
            },
        )
    )
    db.commit()


def _latest(db: Session) -> Optional[MoomooConnectionCheck]:
    return db.scalar(select(MoomooConnectionCheck).order_by(desc(MoomooConnectionCheck.id)).limit(1))


def _status(row: Optional[MoomooConnectionCheck], settings: Settings):
    if row is None:
        return {
            "enabled": settings.moomoo_enabled,
            "sdk_installed": bool(_manager(settings).sdk_version()),
            "opend_reachable": False,
            "opend_logged_in": False,
            "quote_available": False,
            "paper_account_found": False,
            "live_account_found": False,
            "order_submission_enabled": False,
            "live_trading_enabled": False,
            "status_message_zh": "尚未执行Moomoo能力检查",
        }
    capabilities = row.quote_capabilities_json or {}
    return {
        "enabled": settings.moomoo_enabled,
        "sdk_installed": bool(row.sdk_version),
        "opend_reachable": row.opend_reachable,
        "opend_logged_in": row.opend_logged_in,
        "quote_available": bool(capabilities.get("quote_context_available")),
        "paper_account_found": row.paper_account_found,
        "live_account_found": row.live_account_found,
        "order_submission_enabled": False,
        "live_trading_enabled": False,
        "status_message_zh": row.status_message_zh,
    }


@router.get("/status")
def status(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    return _status(_latest(db), settings)


@router.post("/check")
def check(
    request: CheckRequest,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    report = _manager(settings).inspect(request.symbols, enabled=settings.moomoo_enabled)
    _save_report(db, report)
    return report.safe_dict()


@router.get("/capabilities")
def capabilities(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    row = _latest(db)
    if row is None:
        return {"status_code": "not_checked", "status_message_zh": "尚未执行Moomoo能力检查"}
    return {
        "checked_at": row.checked_at,
        "opend_reachable": row.opend_reachable,
        "opend_logged_in": row.opend_logged_in,
        "sdk_version": row.sdk_version,
        "opend_version": row.opend_version,
        "quote_capabilities": row.quote_capabilities_json,
        "paper_account_found": row.paper_account_found,
        "live_account_found": row.live_account_found,
        "order_submission_enabled": False,
        "live_trading_enabled": False,
        "errors": row.errors_json,
        "warnings": row.warnings_json,
        "status_code": row.status_code,
        "status_message_zh": row.status_message_zh,
    }
