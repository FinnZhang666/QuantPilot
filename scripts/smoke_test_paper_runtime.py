"""Run one isolated Phase 4 paper cycle without enabling external runtimes."""

import json

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.database.models import (
    SystemEquitySnapshot, SystemPaperAccount, SystemPaperFill,
    SystemPaperOrder, SystemPaperPosition,
)
from app.database.session import get_session_factory
from app.paper_runtime.manager import RuntimeManager


def main():
    base = get_settings()
    settings = base.model_copy(update={
        "runtime_manager_enabled": True,
        "paper_trading_enabled": True,
        "paper_trading_autostart": False,
        "review_runtime_enabled": True,
        "strategy_scoreboard_enabled": True,
        "telegram_enabled": False,
        "ai_companion_enabled": False,
        "realtime_runtime_enabled": False,
        "moomoo_allow_order_submission": False,
        "moomoo_live_trading_enabled": False,
    })
    manager = RuntimeManager(settings, get_session_factory())
    result = manager.process_once()
    db = get_session_factory()()
    try:
        models = (
            SystemPaperAccount, SystemPaperOrder, SystemPaperFill,
            SystemPaperPosition, SystemEquitySnapshot,
        )
        counts = {
            model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in models
        }
        integrity = {
            model.__tablename__: db.execute(text(
                "PRAGMA integrity_check('%s')" % model.__tablename__
            )).scalar()
            for model in models
        }
        foreign_key_issues = sum(
            len(db.execute(text(
                "PRAGMA foreign_key_check('%s')" % model.__tablename__
            )).all())
            for model in models
        )
    finally:
        db.close()
    print(json.dumps({
        "status": "ok", "paper": result["paper"], "review": result["review"],
        "statistics": result["statistics"],
        "external_transport": {"telegram": False, "gemini": False, "opend_realtime": False},
        "counts": counts, "integrity": integrity,
        "foreign_key_issues": foreign_key_issues,
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
