from datetime import datetime, timezone

from app.database.models import QmrSignalDelivery, TelegramRuntimeMessageLog
from app.qmr_live.formatter import qmr_signal_message
from app.telegram_product.bot_profiles import load_bot_profiles


class QmrTelegramNotifier:
    def __init__(self, repository, settings, transport):
        self.repository, self.settings, self.transport = repository, settings, transport

    def send(self, signal, event_type):
        if not self.settings.telegram_enabled:
            return []
        research = signal.signal_mode == "PAPER"
        profiles = {profile.alias: profile for profile in load_bot_profiles(self.settings) if profile.enabled and profile.token}
        default = next(iter(profiles.values()), None)
        results = []
        for recipient in self.repository.recipients(research):
            profile = profiles.get(recipient["bot_alias"]) or default
            if profile is None: continue
            chat_id = recipient["chat_id"]
            if self.repository.delivery(signal.signal_id, chat_id, event_type): continue
            row = QmrSignalDelivery(signal_id=signal.signal_id, chat_id=chat_id,
                bot_alias=profile.alias, event_type=event_type, status="PENDING")
            self.repository.save_delivery(row)
            try:
                message = qmr_signal_message(signal, recipient["language"], event_type == "INVALIDATED")
                response = self.transport.send_message(profile.token, message.as_payload(chat_id))
                row.status, row.sent_at = "SUCCESS", datetime.now(timezone.utc)
                row.telegram_message_id = str((response.get("result") or {}).get("message_id") or "") or None
            except Exception as exc:
                row.status, row.error_code = "FAILED", type(exc).__name__
            self.repository.db.add(TelegramRuntimeMessageLog(bot_alias=profile.alias,
                direction="OUTBOUND", event_type="QMR_" + event_type, chat_id=chat_id,
                telegram_message_id=row.telegram_message_id, language=recipient["language"],
                status=row.status, error_code=row.error_code,
                payload_summary_json={"signal_id": signal.signal_id}))
            self.repository.commit(); results.append(row.status)
        return results
