"""Send one controlled administrator notification to a previously bound admin."""

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.telegram_product.bot_profiles import load_bot_profiles
from app.telegram_runtime.service import TelegramProductService
from app.telegram_runtime.transport import TelegramBotTransport


def main():
    settings = get_settings()
    profile = next((
        item for item in load_bot_profiles(settings) if item.enabled and item.token
    ), None)
    if profile is None:
        print({"status": "SKIPPED", "reason": "No runnable Bot"})
        return 0
    transport = TelegramBotTransport(
        max(settings.telegram_timeout_seconds, settings.telegram_poll_timeout_seconds + 5),
        settings.telegram_max_retries,
    )
    with get_session_factory()() as db:
        sent = TelegramProductService(db, settings, transport)._notify_admin_event(
            profile, "PHASE5_SMOKE", "Administrator notification delivery is ready.",
        )
    print({"status": "SUCCESS" if sent else "SKIPPED", "admin_notification_sent": sent})
    return 0 if sent else 2


if __name__ == "__main__":
    raise SystemExit(main())
