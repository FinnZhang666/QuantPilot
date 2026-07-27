import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import Notification
from app.notifications.base import NotificationProvider


@dataclass
class NotificationResult:
    status: str
    error: Optional[str] = None


class TelegramNotificationProvider(NotificationProvider):
    """Outbound-only Telegram provider. There are deliberately no listener APIs."""

    def __init__(self, settings: Settings, db: Optional[Session] = None):
        self.settings = settings
        self.db = db

    async def send(self, message: str) -> NotificationResult:
        return await self.send_text(message)

    async def send_text(self, message: str) -> NotificationResult:
        if not self.settings.telegram_enabled:
            return NotificationResult(status="disabled")
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        error = None
        for attempt in range(self.settings.telegram_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.settings.telegram_timeout_seconds) as client:
                    response = await client.post(
                        url,
                        json={"chat_id": self.settings.telegram_chat_id, "text": message},
                    )
                    response.raise_for_status()
                result = NotificationResult(status="sent")
                self._record(message, result)
                return result
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                error = type(exc).__name__
                if attempt < self.settings.telegram_max_retries:
                    await asyncio.sleep(min(2**attempt, 4))
        result = NotificationResult(status="failed", error=error)
        self._record(message, result)
        return result

    def _record(self, message: str, result: NotificationResult) -> None:
        if self.db is None:
            return
        self.db.add(
            Notification(
                channel="telegram",
                event_type="text",
                subject="Telegram notification",
                message=message,
                status=result.status,
                error_message=result.error,
                sent_at=datetime.now(timezone.utc) if result.status == "sent" else None,
            )
        )
        self.db.commit()
