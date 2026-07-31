#!/usr/bin/env python3
import asyncio

from app.core.config import get_settings
from app.notifications.telegram import TelegramNotificationProvider


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_enabled:
        print("Telegram is disabled. Configure .env manually before a real test.")
        return
    result = await TelegramNotificationProvider(settings).send_text(
        "Trade Companion connection test"
    )
    print(f"Telegram result: {result.status}")


if __name__ == "__main__":
    asyncio.run(main())
