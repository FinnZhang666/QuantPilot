from sqlalchemy import select

from app.core.config import Settings
from app.database.models import (
    PortfolioWatchlist,
    TelegramAdminRecord,
    TelegramAIInvocation,
    TelegramFeedbackRecord,
    TelegramRuntimeUser,
)
from app.telegram_product.bot_profiles import load_bot_profiles, synchronize_registry
from app.telegram_runtime.renderer import (
    ai_message,
    feedback_categories,
    language_picker,
    more,
    render_ai_html,
    welcome,
)
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
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_TRADE_COMPANION_AI", "test:production")
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


def select_language(service, profile, language="zh-CN"):
    return service.handle_update(profile, callback_update("language:" + language))


def test_renderer_is_shared_by_preview_and_real(monkeypatch):
    profile = load_bot_profiles(settings(monkeypatch))[0]
    message = welcome(profile, "zh-CN")
    assert message.as_payload() == message.as_payload()
    assert "陪你走过每一次交易" in message.text
    assert len(message.reply_markup["inline_keyboard"]) == 2
    assert more("zh-CN").reply_markup
    assert feedback_categories("en-US").reply_markup
    assert language_picker().reply_markup


def test_first_start_binds_admin_then_requires_language_selection(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    chat_id, result = service.handle_update(profile, start_update())
    admin = db.scalar(select(TelegramAdminRecord).where(TelegramAdminRecord.username == "ADHD360"))
    user = db.scalar(select(TelegramRuntimeUser).where(TelegramRuntimeUser.telegram_user_id == "100"))
    assert chat_id == "100"
    assert result.text == "请选择语言 / Choose your language"
    assert admin.telegram_user_id == "100"
    assert user.pending_context_json["language_selected"] is False


def test_language_selection_persists_and_repeated_start_uses_it(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    _, selected = select_language(service, profile, "en-US")
    user = db.scalar(select(TelegramRuntimeUser).where(TelegramRuntimeUser.telegram_user_id == "100"))
    assert user.language == "en-US"
    assert user.pending_context_json["language_selected"] is True
    assert "With you through every trade" in selected.text
    _, repeated = service.handle_update(profile, start_update("normal_user"))
    assert "With you through every trade" in repeated.text


def test_every_required_callback_has_a_real_response(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    select_language(service, profile)
    for action in (
        "analyze", "portfolio", "market", "feedback", "language", "review",
        "history", "watchlist", "holding", "more", "help", "updates", "about",
    ):
        chat_id, result = service.handle_update(profile, callback_update(action))
        assert chat_id == "100"
        assert result and result.text


def test_expired_callback_ack_does_not_block_watchlist_add_prompt(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]

    def sender(_token, method, _payload):
        if method == "answerCallbackQuery":
            return {"ok": False, "error_code": 400}
        return {"ok": True, "result": {"message_id": 10}}

    service = TelegramProductService(
        db, cfg, TelegramBotTransport(sender=sender, max_retries=0),
    )
    service.handle_update(profile, start_update("normal_user"))
    select_language(service, profile, "en-US")
    _, result = service.handle_update(profile, callback_update("watchlist:add"))
    assert "Enter a stock symbol" in result.text


def test_navigation_callback_clears_previous_pending_action(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    select_language(service, profile, "en-US")
    service.handle_update(profile, callback_update("analyze"))
    user = db.scalar(select(TelegramRuntimeUser).where(
        TelegramRuntimeUser.telegram_user_id == "100",
    ))
    assert user.pending_action == "ANALYZE"
    service.handle_update(profile, callback_update("watchlist"))
    assert user.pending_action is None


def test_watchlist_add_flow_creates_default_portfolio_and_persists_symbol(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    select_language(service, profile, "en-US")
    _, page = service.handle_update(profile, callback_update("watchlist"))
    assert any(
        button["callback_data"] == "tc:watchlist:add"
        for row in page.reply_markup["inline_keyboard"] for button in row
    )
    _, prompt = service.handle_update(profile, callback_update("watchlist:add"))
    assert "Enter a stock symbol" in prompt.text
    _, result = service.handle_update(profile, {
        "update_id": 5,
        "message": {
            "text": "pltr", "chat": {"id": 100},
            "from": {"id": 100, "username": "normal_user"},
        },
    })
    row = db.scalar(select(PortfolioWatchlist))
    assert row.symbol == "PLTR" and "PLTR" in result.text


def test_watchlist_add_flow_rejects_duplicate(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    select_language(service, profile, "en-US")
    for update_id in (5, 6):
        service.handle_update(profile, callback_update("watchlist:add"))
        _, result = service.handle_update(profile, {
            "update_id": update_id,
            "message": {
                "text": "PLTR", "chat": {"id": 100},
                "from": {"id": 100, "username": "normal_user"},
            },
        })
    assert "already on your watchlist" in result.text
    assert len(list(db.scalars(select(PortfolioWatchlist)))) == 1


def test_watchlist_add_accepts_space_comma_and_newline_batch(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    select_language(service, profile, "en-US")
    service.handle_update(profile, callback_update("watchlist:add"))
    _, result = service.handle_update(profile, {
        "update_id": 12,
        "message": {
            "text": "MULL, SPCX\nNOK", "chat": {"id": 100},
            "from": {"id": 100, "username": "normal_user"},
        },
    })
    rows = list(db.scalars(select(PortfolioWatchlist).order_by(PortfolioWatchlist.symbol)))
    assert [row.symbol for row in rows] == ["MULL", "NOK", "SPCX"]
    assert all(symbol in result.text for symbol in ("MULL", "SPCX", "NOK"))


def test_feedback_is_persisted_and_admin_notification_is_attempted(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    fake = FakeTelegram()
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=fake))
    service.handle_update(profile, start_update())
    select_language(service, profile)
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


def test_ai_disabled_uses_fallback_and_records_invocation(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    select_language(service, profile)
    _, result = service.handle_update(profile, {
        "update_id": 4,
        "message": {
            "text": "PLTR", "chat": {"id": 100},
            "from": {"id": 100, "username": "normal_user"},
        },
    })
    assert "AI 暂时不可用" in result.text
    assert "QuantPilot" not in result.text
    row = db.scalar(select(TelegramAIInvocation))
    assert row.status == "FALLBACK" and row.input_hash


def test_batch_ai_analysis_accepts_comma_space_and_newline(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    select_language(service, profile, "en-US")
    service.handle_update(profile, callback_update("analyze"))
    _, result = service.handle_update(profile, {
        "update_id": 7,
        "message": {
            "text": "PLTR, MULL\nSOXL", "chat": {"id": 100},
            "from": {"id": 100, "username": "normal_user"},
        },
    })
    assert all(symbol in result.text for symbol in ("PLTR", "MULL", "SOXL"))
    assert len(list(db.scalars(select(TelegramAIInvocation)))) == 3
    assert len(result.text) <= 4096


def test_batch_ai_analysis_is_deduplicated_and_limited_to_five():
    symbols = TelegramProductService._parse_symbols(
        "PLTR,pltr MULL SOXL QQQ SPY DIA",
    )
    assert symbols == ["PLTR", "MULL", "SOXL", "QQQ", "SPY"]


def test_ai_followup_uses_latest_symbol_instead_of_welcome(db, monkeypatch):
    cfg = settings(monkeypatch)
    profile = synchronize_registry(db, cfg)[0]
    service = TelegramProductService(db, cfg, TelegramBotTransport(sender=FakeTelegram()))
    service.handle_update(profile, start_update("normal_user"))
    select_language(service, profile, "en-US")
    service.handle_update(profile, callback_update("analyze"))
    service.handle_update(profile, {
        "update_id": 8,
        "message": {
            "text": "PLTR", "chat": {"id": 100},
            "from": {"id": 100, "username": "normal_user"},
        },
    })
    _, followup = service.handle_update(profile, {
        "update_id": 9,
        "message": {
            "text": "What is the main risk?", "chat": {"id": 100},
            "from": {"id": 100, "username": "normal_user"},
        },
    })
    assert "STOCK_FOLLOW_UP" in followup.text
    assert "What is the main risk?" in followup.text
    assert "With you through every trade" not in followup.text
    assert len(list(db.scalars(select(TelegramAIInvocation)))) == 2


def test_ai_followup_redacts_secrets():
    fake_token = "1234567890:" + "A" * 35
    result = TelegramProductService._safe_followup_question(
        "token=%s password=secret" % fake_token,
    )
    assert fake_token not in result
    assert "password=secret" not in result


def test_ai_html_renderer_removes_markdown_stars_and_escapes_html():
    source = "# **MULL** 分析\n***\n* 最新价格：16.48\n<script>alert(1)</script>\n*italic*"
    rendered = render_ai_html(source, "zh-CN")
    assert "*" not in rendered and "#" not in rendered
    assert "<b>MULL</b>" in rendered
    assert "• 最新价格：16.48" in rendered
    assert "────────" in rendered
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert "Trade Companion" in rendered and "QuantPilot" not in rendered
    assert len(rendered) <= 4096
    assert ai_message(source, "zh-CN").text == rendered


def test_ai_html_renderer_honors_telegram_length_limit():
    rendered = render_ai_html("* item\n" * 2000, "en-US")
    assert len(rendered) <= 4096
    assert "*" not in rendered and "#" not in rendered
    assert "Disclaimer:" in rendered


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
