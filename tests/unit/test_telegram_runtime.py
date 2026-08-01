from sqlalchemy import select

from app.core.config import Settings
from app.database.models import (
    TelegramAdminRecord,
    TelegramAIInvocation,
    TelegramFeedbackRecord,
    TelegramRuntimeUser,
)
from app.telegram_product.bot_profiles import load_bot_profiles, synchronize_registry
from app.telegram_runtime.renderer import feedback_categories, language_picker, more, welcome
from app.telegram_runtime.service import TelegramProductService
from app.telegram_runtime.transport import TelegramBotTransport, TelegramTransportError


class FakeTelegram:
    def __init__(self):
        self.calls = []

    def __call__(self, token, method, payload):
        self.calls.append((method, payload))
        if method == "getUpdates":
            return {"ok": True, "result": []}
        return {"ok": True, "result": {"message_id": 10}}


def settings(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_TRADE_COMPANION_ZH", "test:zh")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_AI_STOCK_ANALYZE_EN", "test:en")
    return Settings(_env_file=None, dashboard_readonly_public=True)


def start_update(username="ADHD360"):
    return {
        "update_id": 1,
        "message": {
            "text": "/start", "chat": {"id": 100},
            "from": {"id": 100, "username": username, "first_name": "Admin"},
        },
    }


def callback_update(action):
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb-1", "data": "tc:" + action,
            "from": {"id": 100, "username": "ADHD360"},
            "message": {"chat": {"id": 100}},
        },
    }


def test_renderer_is_shared_by_preview_and_real(monkeypatch):
    profile = load_bot_profiles(settings(monkeypatch))[0]
    message = welcome(profile)
    assert message.as_payload() == message.as_payload()
    assert message.text == profile.welcome
    assert len(message.reply_markup["inline_keyboard"]) == 2
    assert more("zh-CN").reply_markup
    assert feedback_categories("en-US").reply_markup
    assert language_picker().reply_markup


def test_start_binds_seeded_admin_and_returns_final_welcome(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    fake = FakeTelegram()
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=fake))
    chat_id, result = service.handle_update(profile, start_update())
    admin = db.scalar(select(TelegramAdminRecord).where(TelegramAdminRecord.username == "ADHD360"))
    assert chat_id == "100"
    assert result.text == profile.welcome
    assert admin.telegram_user_id == "100"


def test_every_required_callback_has_a_real_response(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    for action in (
        "analyze", "portfolio", "market", "feedback", "language", "review",
        "history", "watchlist", "holding", "more",
    ):
        chat_id, result = service.handle_update(profile, callback_update(action))
        assert chat_id == "100"
        assert result and result.text


def test_feedback_is_persisted_and_admin_notification_is_attempted(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    fake = FakeTelegram()
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=fake))
    service.handle_update(profile, start_update())
    service.handle_update(profile, callback_update("feedback:BUG"))
    service.handle_update(profile, {
        "update_id": 3,
        "message": {
            "text": "button does not respond", "chat": {"id": 100},
            "from": {"id": 100, "username": "ADHD360"},
        },
    })
    row = db.scalar(select(TelegramFeedbackRecord))
    assert row.category == "BUG" and row.admin_notified is True
    assert any(method == "sendMessage" for method, _ in fake.calls)


def test_language_switch_is_immediate(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    _, result = service.handle_update(profile, callback_update("language:en-US"))
    user = db.scalar(select(TelegramRuntimeUser).where(TelegramRuntimeUser.telegram_user_id == "100"))
    assert user.language == "en-US"
    assert "English" in result.text


def test_ai_disabled_uses_fallback_and_records_invocation(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    _, result = service.handle_update(profile, {
        "update_id": 4,
        "message": {
            "text": "PLTR", "chat": {"id": 100},
            "from": {"id": 100, "username": "normal_user"},
        },
    })
    assert "AI 暂时不可用" in result.text
    row = db.scalar(select(TelegramAIInvocation))
    assert row.status == "FALLBACK" and row.input_hash


def test_transport_redacts_failures():
    def fail(*args):
        raise RuntimeError("secret-token")

    transport = TelegramBotTransport(sender=fail)
    try:
        transport.call("secret-token", "getMe")
    except TelegramTransportError as exc:
        assert "secret-token" not in str(exc)
    else:
        raise AssertionError("expected transport error")
