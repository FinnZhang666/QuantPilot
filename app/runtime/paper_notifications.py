"""Idempotent Telegram notifications for system paper-trading events."""

import html
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy import select

from app.database.models import (
    SystemPaperAuditEvent,
    SystemPaperPosition,
    TelegramRuntimeMessageLog,
    TelegramRuntimeUser,
)
from app.telegram_product.bot_profiles import load_bot_profiles
from app.telegram_runtime.renderer import TelegramMessage
from app.telegram_runtime.transport import TelegramBotTransport


class PaperEventNotificationDispatcher:
    EVENT_TYPES = ("POSITION_OPENED", "POSITION_CLOSED", "REVIEW_GENERATED")

    def __init__(self, settings, session_factory, transport: Optional[TelegramBotTransport] = None):
        self.settings = settings
        self.session_factory = session_factory
        self.transport = transport or TelegramBotTransport(
            settings.telegram_timeout_seconds, settings.telegram_max_retries,
        )

    def dispatch_pending(self) -> Dict[str, object]:
        if not (self.settings.telegram_enabled and self.settings.telegram_runtime_enabled):
            return {"status": "DISABLED", "sent": 0, "skipped": 0, "failed": 0}
        profiles = {
            item.alias: item for item in load_bot_profiles(self.settings)
            if item.enabled and item.token
        }
        if not profiles:
            return {"status": "DISABLED", "sent": 0, "skipped": 0, "failed": 0}
        db = self.session_factory()
        try:
            since = datetime.now(timezone.utc) - timedelta(days=7)
            events = list(db.scalars(select(SystemPaperAuditEvent).where(
                SystemPaperAuditEvent.event_type.in_(self.EVENT_TYPES),
                SystemPaperAuditEvent.timestamp >= since,
            ).order_by(SystemPaperAuditEvent.id).limit(500)))
            users = list(db.scalars(select(TelegramRuntimeUser).where(
                TelegramRuntimeUser.status == "ACTIVE",
            )))
            sent = skipped = failed = 0
            for event in events:
                position = db.get(SystemPaperPosition, event.position_id) if event.position_id else None
                for user in users:
                    profile = profiles.get(user.last_bot_alias) or profiles.get("trade_companion_ai")
                    if profile is None:
                        skipped += 1
                        continue
                    key = "paper:%s:%s" % (event.id, user.id)
                    exists = db.scalar(select(TelegramRuntimeMessageLog.id).where(
                        TelegramRuntimeMessageLog.direction == "OUTBOUND",
                        TelegramRuntimeMessageLog.event_type == event.event_type,
                        TelegramRuntimeMessageLog.update_id == key,
                        TelegramRuntimeMessageLog.chat_id == user.chat_id,
                        TelegramRuntimeMessageLog.status == "SUCCESS",
                    ).limit(1))
                    if exists:
                        skipped += 1
                        continue
                    started = time.perf_counter()
                    try:
                        response = self.transport.send_message(
                            profile.token,
                            TelegramMessage(self._render(event, position, user.language)).as_payload(user.chat_id),
                        )
                        message_id = str((response.get("result") or {}).get("message_id") or "") or None
                        status, error_code = "SUCCESS", None
                        sent += 1
                    except Exception:
                        message_id = None
                        status, error_code = "FAILED", "TELEGRAM_DELIVERY_FAILED"
                        failed += 1
                    db.add(TelegramRuntimeMessageLog(
                        bot_alias=profile.alias, direction="OUTBOUND",
                        event_type=event.event_type, telegram_user_id=user.telegram_user_id,
                        chat_id=user.chat_id, update_id=key,
                        telegram_message_id=message_id, language=user.language,
                        status=status, latency_ms=int((time.perf_counter() - started) * 1000),
                        error_code=error_code, error_message=None,
                        payload_summary_json={"paper_event_id": event.id, "position_id": event.position_id},
                    ))
                    db.commit()
            return {"status": "SUCCESS", "sent": sent, "skipped": skipped, "failed": failed}
        finally:
            db.close()

    @classmethod
    def _render(cls, event, position, language: str) -> str:
        details = event.details_json or {}
        symbol = cls._safe(position.symbol if position else details.get("symbol") or "-")
        direction = cls._safe(position.direction if position else details.get("direction") or "-")
        if language == "en-US":
            title = {"POSITION_OPENED": "Paper position opened", "POSITION_CLOSED": "Paper position closed", "REVIEW_GENERATED": "Trade review ready"}[event.event_type]
            lines = ["<b>%s</b>" % title, "Symbol: %s" % symbol, "Direction: %s" % direction]
            cls._append_position(lines, position, english=True)
            if event.event_type == "POSITION_CLOSED":
                lines += ["Exit reason: %s" % cls._safe(details.get("reason") or getattr(position, "exit_reason", None) or "-"), "Realized P/L: %s" % cls._safe(details.get("realized_pnl") or getattr(position, "realized_pnl", None) or "-")]
            if event.event_type == "REVIEW_GENERATED":
                lines.append("Review result: %s" % cls._safe(details.get("result") or "-"))
            lines += ["????????", "System paper trade only. This is not a broker order or investment advice. Verify independently before following."]
        else:
            title = {"POSITION_OPENED": "???????", "POSITION_CLOSED": "???????", "REVIEW_GENERATED": "???????"}[event.event_type]
            lines = ["<b>%s</b>" % title, "???%s" % symbol, "???%s" % direction]
            cls._append_position(lines, position, english=False)
            if event.event_type == "POSITION_CLOSED":
                lines += ["?????%s" % cls._safe(details.get("reason") or getattr(position, "exit_reason", None) or "-"), "??????%s" % cls._safe(details.get("realized_pnl") or getattr(position, "realized_pnl", None) or "-")]
            if event.event_type == "REVIEW_GENERATED":
                lines.append("?????%s" % cls._safe(details.get("result") or "-"))
            lines += ["????????", "?????????????????????????????????????"]
        return "\n".join(lines).replace("*", "").replace("#", "")[:4096]

    @classmethod
    def _append_position(cls, lines, position, english=False):
        if position is None:
            return
        labels = ("Entry", "Quantity", "Stop", "Targets") if english else ("?????", "??", "??", "???")
        lines.append("%s: %s" % (labels[0], cls._number(position.average_entry)))
        lines.append("%s: %s" % (labels[1], cls._number(position.initial_quantity or position.quantity)))
        lines.append("%s: %s" % (labels[2], cls._number(position.stop_price)))
        targets = ", ".join(cls._number(value) for value in (position.targets_json or [])) or "-"
        lines.append("%s: %s" % (labels[3], targets))

    @staticmethod
    def _number(value) -> str:
        if value is None:
            return "-"
        try:
            number = Decimal(str(value))
            return format(number.normalize(), "f")
        except Exception:
            return html.escape(str(value), quote=False)

    @staticmethod
    def _safe(value) -> str:
        return html.escape(str(value), quote=False).replace("*", "").replace("#", "")[:500]
