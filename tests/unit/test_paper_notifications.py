from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.database.models import (
    SystemPaperAuditEvent,
    TelegramRuntimeMessageLog,
    TelegramRuntimeUser,
)
from app.runtime.paper_notifications import PaperEventNotificationDispatcher
from app.telegram_runtime.transport import TelegramBotTransport


class FakeSender:
    def __init__(self):
        self.calls = []

    def __call__(self, token, method, payload):
        self.calls.append((token, method, payload))
        return {"ok": True, "result": {"message_id": len(self.calls)}}


def config():
    return Settings(
        _env_file=None,
        telegram_enabled=True,
        telegram_runtime_enabled=True,
        telegram_bot_token_trade_companion_ai="test:paper-notify",
        telegram_bot_token_quantpilot_ai="",
        telegram_bot_token_ai_stock_analyze="",
        telegram_bot_token_jiaoyi_banlv="",
        telegram_bot_token_fenxi_gupiao="",
    )


def test_dispatches_to_every_active_user_once(db):
    db.add_all([
        TelegramRuntimeUser(
            telegram_user_id="101", chat_id="201", language="zh-CN",
            last_bot_alias="trade_companion_ai", status="ACTIVE",
        ),
        TelegramRuntimeUser(
            telegram_user_id="102", chat_id="202", language="en-US",
            last_bot_alias="trade_companion_ai", status="ACTIVE",
        ),
        TelegramRuntimeUser(
            telegram_user_id="103", chat_id="203", language="zh-CN",
            last_bot_alias="trade_companion_ai", status="DISABLED",
        ),
        SystemPaperAuditEvent(
            event_type="POSITION_OPENED", timestamp=datetime.now(timezone.utc),
            details_json={"symbol": "PLTR", "direction": "LONG"},
        ),
    ])
    db.commit()
    sender = FakeSender()
    dispatcher = PaperEventNotificationDispatcher(
        config(), sessionmaker(bind=db.bind, expire_on_commit=False),
        TelegramBotTransport(sender=sender, max_retries=0),
    )

    first = dispatcher.dispatch_pending()
    second = dispatcher.dispatch_pending()

    assert first == {"status": "SUCCESS", "sent": 2, "skipped": 0, "failed": 0}
    assert second == {"status": "SUCCESS", "sent": 0, "skipped": 2, "failed": 0}
    assert len(sender.calls) == 2
    assert {call[2]["chat_id"] for call in sender.calls} == {"201", "202"}
    assert all("*" not in call[2]["text"] and "#" not in call[2]["text"] for call in sender.calls)
    assert all("paper" in call[2]["text"].lower() or "????" in call[2]["text"] for call in sender.calls)
    logs = db.query(TelegramRuntimeMessageLog).filter_by(status="SUCCESS").all()
    assert len(logs) == 2
    assert len({row.update_id for row in logs}) == 2


def test_position_message_contains_system_levels_and_escapes_html():
    event = SimpleNamespace(
        event_type="POSITION_CLOSED",
        details_json={"reason": "STOP < unsafe", "realized_pnl": "-12.5"},
    )
    position = SimpleNamespace(
        symbol="MULL#", direction="LONG*", average_entry="16.48",
        initial_quantity="10", quantity="0", stop_price="15.20",
        targets_json=["18", "20"], exit_reason="STOP", realized_pnl="-12.5",
    )
    text = PaperEventNotificationDispatcher._render(event, position, "zh-CN")
    assert "16.48" in text and "15.2" in text and "18, 20" in text
    assert "STOP &lt; unsafe" in text
    assert "*" not in text and "#" not in text
    assert "??????" in text
