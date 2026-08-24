from app.database.models import QmrExitEvaluation, TelegramRuntimeMessageLog
from app.qmr_exit.formatter import qmr_exit_message
from app.qmr_live.repository import QmrLiveRepository
from app.telegram_product.bot_profiles import load_bot_profiles


class QmrExitNotifier:
    def __init__(self, db, settings, transport):
        self.db, self.settings, self.transport = db, settings, transport

    def send_event(self, event):
        if event.notification_status != "PENDING": return []
        if not self.settings.telegram_enabled:
            event.notification_status = "DISABLED"; self.db.commit(); return []
        evaluation = self.db.get(QmrExitEvaluation, event.evaluation_id)
        profiles = {item.alias: item for item in load_bot_profiles(self.settings) if item.enabled and item.token}
        default = next(iter(profiles.values()), None)
        results = []
        for recipient in QmrLiveRepository(self.db).recipients(False):
            profile = profiles.get(recipient["bot_alias"]) or default
            if profile is None: continue
            status, message_id, error = "SUCCESS", None, None
            try:
                response = self.transport.send_message(profile.token,
                    qmr_exit_message(evaluation, recipient["language"]).as_payload(recipient["chat_id"]))
                message_id = str((response.get("result") or {}).get("message_id") or "") or None
            except Exception as exc:
                status, error = "FAILED", type(exc).__name__
            self.db.add(TelegramRuntimeMessageLog(bot_alias=profile.alias, direction="OUTBOUND",
                event_type="QMR_EXIT_" + event.state, chat_id=recipient["chat_id"],
                telegram_message_id=message_id, language=recipient["language"], status=status,
                error_code=error, payload_summary_json={"exit_event_id": event.id,
                    "evaluation_id": event.evaluation_id, "symbol": event.symbol}))
            results.append(status)
        event.notification_status = "SUCCESS" if results and all(x == "SUCCESS" for x in results) else (
            "FAILED" if results else "NO_RECIPIENT")
        self.db.commit()
        return results
