import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.database.models import (
    RuntimeStatus,
    TelegramBotProfileRecord,
    TelegramProfileSyncLog,
    TelegramRuntimeMessageLog,
)
from app.database.session import get_session_factory
from app.telegram_product.bot_profiles import (
    TelegramBotProfile,
    load_bot_profiles,
    synchronize_registry,
    validate_profile,
)
from app.telegram_product.profile_sync import build_sync_steps
from app.telegram_runtime.service import TelegramProductService
from app.telegram_runtime.transport import TelegramBotTransport


logger = logging.getLogger(__name__)


class TelegramRuntimeManager:
    """One process/thread coordinates every configured Bot profile."""

    def __init__(self, settings: Settings, transport: Optional[TelegramBotTransport] = None):
        self.settings = settings
        self.transport = transport or TelegramBotTransport(
            max(
                settings.telegram_timeout_seconds,
                float(settings.telegram_poll_timeout_seconds + 5),
            ),
            settings.telegram_max_retries,
        )
        self._status = "STOPPED"
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._guard = threading.RLock()
        self._last_success_at: Optional[datetime] = None
        self._last_failure_at: Optional[datetime] = None
        self._last_error_code: Optional[str] = None

    @property
    def status(self) -> str:
        return self._status

    def initialize_registry(self) -> List[TelegramBotProfile]:
        with get_session_factory()() as db:
            return synchronize_registry(db, self.settings)

    def snapshot(self) -> Dict[str, object]:
        profiles = load_bot_profiles(self.settings)
        return {
            "status": self._status,
            "enabled": self.settings.telegram_enabled and self.settings.telegram_runtime_enabled,
            "autostart": self.settings.telegram_runtime_autostart,
            "process_id": os.getpid() if self._status == "RUNNING" else None,
            "bot_count": len(profiles),
            "runtime_bot_count": sum(1 for item in profiles if item.enabled and item.token),
            "configured_bot_count": sum(1 for item in profiles if item.token),
            "last_success_at": self._last_success_at,
            "last_failure_at": self._last_failure_at,
            "last_error_code": self._last_error_code,
            "open_d_realtime": False,
            "broker_trading": False,
            "real_order_calls": 0,
        }

    def start(self) -> Dict[str, object]:
        with self._guard:
            if self._status in {"STARTING", "RUNNING"}:
                return self.snapshot()
            if not self.settings.telegram_enabled or not self.settings.telegram_runtime_enabled:
                raise RuntimeError("Telegram Runtime is disabled by configuration.")
            profiles = self.initialize_registry()
            runnable = [item for item in profiles if item.enabled and item.token]
            if not runnable:
                raise RuntimeError("No enabled Telegram Bot has a configured token.")
            self._status = "STARTING"
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop, name="telegram-multi-bot-runtime", daemon=True,
            )
            self._thread.start()
            self._status = "RUNNING"
            self._write_status("RUNNING")
            return self.snapshot()

    def stop(self) -> Dict[str, object]:
        with self._guard:
            if self._status == "STOPPED":
                return self.snapshot()
            self._status = "STOPPING"
            self._stop.set()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=self.settings.telegram_poll_timeout_seconds + 5)
        with self._guard:
            self._thread = None
            self._status = "STOPPED"
            self._write_status("STOPPED")
        return self.snapshot()

    def run_once(self, poll_timeout: int = 0) -> Dict[str, object]:
        profiles = self.initialize_registry()
        results = []
        for profile in profiles:
            if not profile.enabled:
                results.append({"alias": profile.alias, "status": "DISABLED"})
            elif not profile.token:
                results.append({"alias": profile.alias, "status": "TOKEN_MISSING"})
            else:
                results.append(self._poll_profile(profile, poll_timeout))
        return {"status": "COMPLETED", "bots": results}

    def sync_profiles(self, dry_run: bool = True, alias: Optional[str] = None):
        profiles = self.initialize_registry()
        if alias:
            profiles = [item for item in profiles if item.alias == alias]
            if not profiles:
                raise ValueError("Unknown Telegram bot alias.")
        results = []
        repository_root = __import__("pathlib").Path(__file__).resolve().parents[2]
        with get_session_factory()() as db:
            for profile in profiles:
                errors = validate_profile(profile, repository_root)
                steps = []
                status = "DRY_RUN"
                remote_snapshot = {}
                error_code = None
                if errors:
                    status = "INVALID"
                    error_code = ",".join(errors)
                else:
                    for step in build_sync_steps(profile):
                        item = {"method": step.method, "supported": step.supported, "note": step.note}
                        if not step.supported:
                            item["status"] = "MANUAL_REQUIRED"
                        elif dry_run:
                            item["status"] = "PLANNED"
                        elif not profile.token:
                            item["status"] = "TOKEN_MISSING"
                            status = "TOKEN_MISSING"
                        else:
                            try:
                                response = self.transport.call(profile.token, step.method, step.payload)
                                item["status"] = "SUCCESS"
                                if step.method == "getMe":
                                    remote_snapshot = {
                                        "id": str((response.get("result") or {}).get("id") or ""),
                                        "username": (response.get("result") or {}).get("username"),
                                    }
                            except Exception as exc:
                                item["status"] = "FAILED"
                                status = "FAILED"
                                error_code = type(exc).__name__
                        steps.append(item)
                    if not dry_run and status not in {"FAILED", "TOKEN_MISSING"}:
                        try:
                            audit = self._audit_remote(profile)
                            remote_snapshot.update(audit["remote"])
                            steps.append({
                                "method": "profileAudit", "supported": True,
                                "status": "SUCCESS" if audit["matches"] else "FAILED",
                                "note": "Exact remote profile readback",
                            })
                            status = "COMPLETED" if audit["matches"] else "AUDIT_FAILED"
                            if not audit["matches"]:
                                error_code = "REMOTE_PROFILE_MISMATCH"
                        except Exception as exc:
                            status = "AUDIT_FAILED"
                            error_code = type(exc).__name__
                            steps.append({
                                "method": "profileAudit", "supported": True,
                                "status": "FAILED", "note": "Remote readback failed",
                            })
                row = db.scalar(select(TelegramBotProfileRecord).where(
                    TelegramBotProfileRecord.alias == profile.alias,
                ))
                if row:
                    row.sync_status = status
                    row.last_sync_at = datetime.now(timezone.utc)
                    if remote_snapshot:
                        row.remote_id = remote_snapshot.get("id")
                        row.remote_username = remote_snapshot.get("username")
                db.add(TelegramProfileSyncLog(
                    bot_alias=profile.alias, mode="DRY_RUN" if dry_run else "APPLY",
                    status=status, steps_json=steps, remote_snapshot_json=remote_snapshot,
                    error_code=error_code,
                ))
                results.append({
                    "alias": profile.alias, "status": status,
                    "token_configured": bool(profile.token), "steps": steps,
                    "remote": remote_snapshot, "avatar": "MANUAL_REQUIRED",
                })
            db.commit()
        return {"dry_run": dry_run, "items": results, "total": len(results)}

    def _audit_remote(self, profile: TelegramBotProfile) -> Dict[str, object]:
        name = (self.transport.call(profile.token, "getMyName", {}).get("result") or {}).get("name")
        about = (self.transport.call(
            profile.token, "getMyShortDescription", {},
        ).get("result") or {}).get("short_description")
        description = (self.transport.call(
            profile.token, "getMyDescription", {},
        ).get("result") or {}).get("description")
        commands = self.transport.call(profile.token, "getMyCommands", {}).get("result") or []
        menu_button = self.transport.call(
            profile.token, "getChatMenuButton", {},
        ).get("result") or {}
        expected_commands = [item.__dict__ for item in profile.commands]
        matches = (
            name == profile.display_name
            and about == profile.short_description
            and description == profile.description
            and commands == expected_commands
            and menu_button.get("type") == "commands"
        )
        return {
            "matches": matches,
            "remote": {
                "name": name, "about": about, "description": description,
                "commands": commands, "menu_button": menu_button.get("type"),
                "language": profile.language,
                "welcome_matches_registry": bool(profile.welcome),
                "runtime_enabled": profile.enabled,
                "old_content_detected": not matches,
            },
        }

    def send_smoke(self, alias: str, chat_id: str):
        profile = next((item for item in load_bot_profiles(self.settings) if item.alias == alias), None)
        if profile is None:
            raise ValueError("Unknown Telegram bot alias.")
        result = self.transport.send_message(profile.token, {
            "chat_id": chat_id, "text": profile.welcome, "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": [[
                {"text": item.label, "callback_data": "tc:" + item.action}
                for item in profile.main_menu[:2]
            ], [
                {"text": item.label, "callback_data": "tc:" + item.action}
                for item in profile.main_menu[2:]
            ]]},
        })
        return {"alias": alias, "status": "SENT", "message_id": (result.get("result") or {}).get("message_id")}

    def _run_loop(self):
        while not self._stop.is_set():
            try:
                result = self.run_once(self.settings.telegram_poll_timeout_seconds)
                failed = [item for item in result["bots"] if item["status"] == "FAILED"]
                if failed:
                    self._status = "DEGRADED"
                    self._last_failure_at = datetime.now(timezone.utc)
                    self._last_error_code = failed[0].get("error_code")
                    self._write_status("DEGRADED")
                else:
                    self._status = "RUNNING"
                    self._last_success_at = datetime.now(timezone.utc)
                    self._last_error_code = None
                    self._write_status("RUNNING")
            except Exception as exc:
                self._last_failure_at = datetime.now(timezone.utc)
                self._last_error_code = type(exc).__name__
                logger.error("Telegram Runtime cycle failed code=%s", self._last_error_code)
                self._notify_runtime_error()
            self._stop.wait(self.settings.telegram_poll_interval_seconds)

    def _notify_runtime_error(self) -> None:
        profile = next((
            item for item in load_bot_profiles(self.settings) if item.enabled and item.token
        ), None)
        if profile is None:
            return
        with get_session_factory()() as db:
            try:
                TelegramProductService(db, self.settings, self.transport)._notify_admin_event(
                    profile, "RUNTIME_ERROR", "Telegram Runtime entered a degraded cycle.",
                )
            except Exception:
                return

    def _poll_profile(self, profile: TelegramBotProfile, poll_timeout: int):
        with get_session_factory()() as db:
            record = db.scalar(select(TelegramBotProfileRecord).where(
                TelegramBotProfileRecord.alias == profile.alias,
            ))
            offset = int(record.update_offset or 0) if record else 0
            started = time.perf_counter()
            try:
                response = self.transport.get_updates(profile.token, offset, poll_timeout)
                updates = list(response.get("result") or [])
                service = TelegramProductService(db, self.settings, self.transport)
                sent = 0
                for update in updates:
                    update_id = int(update.get("update_id") or 0)
                    chat_id, message = service.handle_update(profile, update)
                    if chat_id and message:
                        self.transport.send_message(profile.token, message.as_payload(chat_id))
                        sent += 1
                        service.log_message(
                            profile, "OUTBOUND", "BOT_RESPONSE", "SUCCESS", chat_id,
                            str(update_id), int((time.perf_counter() - started) * 1000),
                        )
                    offset = max(offset, update_id + 1)
                if record:
                    record.update_offset = offset
                    record.last_update_at = datetime.now(timezone.utc)
                    record.runtime_status = "RUNNING" if self._status == "RUNNING" else "RUN_ONCE"
                db.commit()
                self._last_success_at = datetime.now(timezone.utc)
                return {"alias": profile.alias, "status": "SUCCESS", "updates": len(updates), "sent": sent}
            except Exception as exc:
                if record:
                    record.runtime_status = "DEGRADED"
                db.add(TelegramRuntimeMessageLog(
                    bot_alias=profile.alias, direction="SYSTEM",
                    event_type="RUNTIME_ERROR", status="FAILED",
                    error_code=type(exc).__name__, error_message=str(exc)[:512],
                    payload_summary_json={},
                ))
                db.commit()
                return {
                    "alias": profile.alias, "status": "FAILED",
                    "error_code": type(exc).__name__,
                }

    def _write_status(self, status: str):
        with get_session_factory()() as db:
            row = db.scalar(select(RuntimeStatus).where(RuntimeStatus.service_name == "telegram_runtime"))
            if row is None:
                row = RuntimeStatus(service_name="telegram_runtime")
                db.add(row)
            row.status = status
            row.last_heartbeat_at = datetime.now(timezone.utc)
            row.metadata_json = {"bot_count": len(load_bot_profiles(self.settings)), "multi_bot": True}
            db.commit()


_runtime: Optional[TelegramRuntimeManager] = None


def get_telegram_runtime(settings: Optional[Settings] = None) -> TelegramRuntimeManager:
    global _runtime
    if _runtime is None:
        _runtime = TelegramRuntimeManager(settings or get_settings())
    return _runtime


def reset_telegram_runtime() -> None:
    global _runtime
    if _runtime is not None and _runtime.status != "STOPPED":
        _runtime.stop()
    _runtime = None
