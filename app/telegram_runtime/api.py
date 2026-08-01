from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.models import (
    TelegramAIInvocation,
    TelegramBotProfileRecord,
    TelegramFeedbackRecord,
    TelegramRuntimeMessageLog,
    TelegramRuntimeUser,
)
from app.database.session import get_db
from app.telegram_product.bot_profiles import load_bot_profiles
from app.telegram_runtime.renderer import feedback_categories, language_picker, more, welcome
from app.telegram_runtime.runtime import get_telegram_runtime


class RuntimeResponse(BaseModel):
    status: str
    enabled: bool
    autostart: bool
    process_id: Optional[int]
    bot_count: int
    runtime_bot_count: int
    configured_bot_count: int
    last_success_at: Optional[datetime]
    last_failure_at: Optional[datetime]
    last_error_code: Optional[str]
    open_d_realtime: bool
    broker_trading: bool
    real_order_calls: int


class RuntimeActionRequest(BaseModel):
    poll_timeout: int = Field(default=0, ge=0, le=50)


class SyncRequest(BaseModel):
    dry_run: bool = True
    alias: Optional[str] = None


class SendSmokeRequest(BaseModel):
    alias: str
    chat_id: str


class FeedbackUpdateRequest(BaseModel):
    status: Optional[str] = None
    reply_status: Optional[str] = None


router = APIRouter(
    prefix="/api/telegram", tags=["Telegram Runtime"],
    dependencies=[Depends(require_read)],
)
internal_router = APIRouter(
    prefix="/internal/telegram", tags=["Internal Telegram Runtime"],
    dependencies=[Depends(require_admin)], include_in_schema=False,
)


@router.get("/runtime", response_model=RuntimeResponse)
def runtime_status(settings: Settings = Depends(get_settings)):
    return get_telegram_runtime(settings).snapshot()


@router.get("/bots")
def bots(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    profiles = load_bot_profiles(settings)
    records = {row.alias: row for row in db.scalars(select(TelegramBotProfileRecord))}
    items = []
    for profile in profiles:
        record = records.get(profile.alias)
        data = profile.safe_summary()
        data.update({
            "about": profile.short_description,
            "description": profile.description,
            "commands": [item.__dict__ for item in profile.commands],
            "menu": [item.__dict__ for item in profile.main_menu],
            "welcome": profile.welcome,
            "runtime_status": record.runtime_status if record else "NOT_INITIALIZED",
            "sync_status": record.sync_status if record else "NEVER_SYNCED",
            "remote_username": record.remote_username if record else None,
        })
        items.append(data)
    return {"items": items, "total": len(items), "secrets_exposed": False}


@router.get("/statistics")
def statistics(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    today = datetime.now(timezone.utc).date().isoformat()
    messages_today = int(db.scalar(select(func.count()).select_from(
        TelegramRuntimeMessageLog,
    ).where(func.date(TelegramRuntimeMessageLog.created_at) == today)) or 0)
    feedback_count = int(db.scalar(select(func.count()).select_from(TelegramFeedbackRecord)) or 0)
    ai_calls = int(db.scalar(select(func.count()).select_from(TelegramAIInvocation)) or 0)
    languages = dict(db.execute(select(
        TelegramRuntimeUser.language, func.count(TelegramRuntimeUser.id),
    ).group_by(TelegramRuntimeUser.language)).all())
    snapshot = get_telegram_runtime(settings).snapshot()
    return {
        "bot_count": snapshot["bot_count"],
        "configured_bot_count": snapshot["configured_bot_count"],
        "messages_today": messages_today,
        "feedback_count": feedback_count,
        "ai_calls": ai_calls,
        "languages": languages,
        "runtime_status": snapshot["status"],
    }


@router.get("/feedback")
def feedback(
    search: Optional[str] = None, category: Optional[str] = None,
    status: Optional[str] = None, reply_status: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = select(TelegramFeedbackRecord, TelegramRuntimeUser).join(
        TelegramRuntimeUser, TelegramRuntimeUser.id == TelegramFeedbackRecord.user_id,
    )
    filters = []
    if search:
        pattern = "%%%s%%" % search
        filters.append(or_(
            TelegramFeedbackRecord.message.ilike(pattern),
            TelegramRuntimeUser.username.ilike(pattern),
        ))
    if category:
        filters.append(TelegramFeedbackRecord.category == category.upper())
    if status:
        filters.append(TelegramFeedbackRecord.status == status.upper())
    if reply_status:
        filters.append(TelegramFeedbackRecord.reply_status == reply_status.upper())
    if filters:
        query = query.where(*filters)
    rows = db.execute(query.order_by(desc(TelegramFeedbackRecord.created_at)).offset(
        (page - 1) * page_size,
    ).limit(page_size)).all()
    return {"items": [{
        "id": item.id, "category": item.category, "message": item.message,
        "status": item.status, "reply_status": item.reply_status,
        "admin_notified": item.admin_notified, "bot_alias": item.bot_alias,
        "language": item.language, "username": user.username,
        "created_at": item.created_at,
    } for item, user in rows], "page": page, "page_size": page_size}


@router.get("/preview/{alias}/{view}")
def preview(alias: str, view: str, settings: Settings = Depends(get_settings)):
    profile = next((item for item in load_bot_profiles(settings) if item.alias == alias), None)
    if profile is None:
        raise HTTPException(404, "Unknown Telegram bot alias.")
    builders = {
        "welcome": lambda: welcome(profile),
        "menu": lambda: welcome(profile),
        "more": lambda: more(profile.language),
        "feedback": lambda: feedback_categories(profile.language),
        "language": language_picker,
    }
    if view not in builders:
        raise HTTPException(404, "Unknown Telegram preview view.")
    message = builders[view]()
    return {
        **message.as_payload(), "alias": profile.alias,
        "preview_equals_real": True, "source": "TELEGRAM_MESSAGE_RENDERER",
    }


@internal_router.post("/runtime/start", response_model=RuntimeResponse)
def start(settings: Settings = Depends(get_settings)):
    try:
        return get_telegram_runtime(settings).start()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@internal_router.post("/runtime/stop", response_model=RuntimeResponse)
def stop(settings: Settings = Depends(get_settings)):
    return get_telegram_runtime(settings).stop()


@internal_router.post("/runtime/run-once")
def run_once(payload: RuntimeActionRequest, settings: Settings = Depends(get_settings)):
    return get_telegram_runtime(settings).run_once(payload.poll_timeout)


@internal_router.post("/sync")
def sync(payload: SyncRequest, settings: Settings = Depends(get_settings)):
    try:
        return get_telegram_runtime(settings).sync_profiles(payload.dry_run, payload.alias)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@internal_router.post("/send-smoke")
def send_smoke(payload: SendSmokeRequest, settings: Settings = Depends(get_settings)):
    try:
        return get_telegram_runtime(settings).send_smoke(payload.alias, payload.chat_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@internal_router.put("/feedback/{feedback_id}")
def update_feedback(
    feedback_id: int, payload: FeedbackUpdateRequest, db: Session = Depends(get_db),
):
    row = db.get(TelegramFeedbackRecord, feedback_id)
    if row is None:
        raise HTTPException(404, "Feedback not found.")
    if payload.status:
        row.status = payload.status.upper()
    if payload.reply_status:
        row.reply_status = payload.reply_status.upper()
    db.commit()
    return {"id": row.id, "status": row.status, "reply_status": row.reply_status}
