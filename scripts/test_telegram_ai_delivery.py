"""Controlled real Gemini -> Telegram delivery smoke test for a bound admin."""

import html
import time

from sqlalchemy import desc, select

from app.core.config import get_settings
from app.database.models import TelegramAdminRecord, TelegramAIInvocation, TelegramRuntimeUser
from app.database.session import get_session_factory
from app.telegram_product.bot_profiles import load_bot_profiles
from app.telegram_runtime.ai import TelegramAIService
from app.telegram_runtime.renderer import TelegramMessage
from app.telegram_runtime.transport import TelegramBotTransport


def main():
    settings = get_settings()
    profile = next((item for item in load_bot_profiles(settings) if item.enabled and item.token), None)
    if profile is None:
        print({"status": "SKIPPED", "reason": "No runnable Bot"})
        return 2
    transport = TelegramBotTransport(
        max(settings.telegram_timeout_seconds, settings.telegram_poll_timeout_seconds + 5),
        settings.telegram_max_retries,
    )
    with get_session_factory()() as db:
        admin = db.scalar(select(TelegramAdminRecord).where(
            TelegramAdminRecord.username == "ADHD360",
            TelegramAdminRecord.telegram_user_id.is_not(None),
        ))
        if admin is None:
            print({"status": "SKIPPED", "reason": "Administrator not bound"})
            return 2
        user = db.scalar(select(TelegramRuntimeUser).where(
            TelegramRuntimeUser.telegram_user_id == admin.telegram_user_id,
        ))
        started = time.perf_counter()
        analysis = TelegramAIService(db, settings).explain(
            "STOCK_ANALYSIS", user.language if user else profile.language,
            profile.alias, user.id if user else None, "PLTR",
        )
        invocation = db.scalar(select(TelegramAIInvocation).order_by(
            desc(TelegramAIInvocation.id),
        ).limit(1))
        transport.send_message(profile.token, TelegramMessage(
            "<b>PLTR · Trade Companion AI</b>\n\n" + html.escape(analysis),
        ).as_payload(admin.telegram_user_id))
        print({
            "status": "SUCCESS", "provider": invocation.provider,
            "model": invocation.model, "ai_status": invocation.status,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "prompt_tokens": invocation.prompt_tokens,
            "completion_tokens": invocation.completion_tokens,
            "telegram_sent": True,
        })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
