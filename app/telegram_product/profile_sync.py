import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from urllib import parse, request

from app.telegram_product.bot_profiles import TelegramBotProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncStep:
    method: str
    payload: Dict[str, object]
    supported: bool = True
    note: str = ""


def build_sync_steps(profile: TelegramBotProfile) -> List[SyncStep]:
    commands = [{"command": item.command, "description": item.description}
                for item in profile.commands]
    return [
        SyncStep("getMe", {}),
        SyncStep("setMyName", {"name": profile.display_name}),
        SyncStep("setMyShortDescription", {"short_description": profile.short_description}),
        SyncStep("setMyDescription", {"description": profile.description}),
        SyncStep("setMyCommands", {"commands": commands}),
        SyncStep("setChatMenuButton", {"menu_button": {"type": "commands"}}),
        SyncStep(
            "setProfilePhoto", {}, supported=False,
            note="Bot profile photos must be configured through BotFather; Bot API has no upload method.",
        ),
    ]


class TelegramProfileSynchronizer:
    def __init__(self, transport: Optional[Callable] = None):
        self.transport = transport or self._http_transport

    def sync(self, profile: TelegramBotProfile, dry_run: bool = True) -> Dict[str, object]:
        result = {
            "alias": profile.alias, "dry_run": dry_run, "enabled": profile.enabled,
            "token_configured": bool(profile.token), "steps": [], "status": "DRY_RUN",
        }
        for step in build_sync_steps(profile):
            item = {"method": step.method, "supported": step.supported, "note": step.note}
            if dry_run or not step.supported:
                item["status"] = "PLANNED" if step.supported else "MANUAL_REQUIRED"
            else:
                if not profile.token:
                    raise ValueError("Bot token is not configured for alias: %s" % profile.alias)
                response = self.transport(profile.token, step.method, step.payload)
                item["status"] = "SUCCESS" if response.get("ok") else "FAILED"
            result["steps"].append(item)
        if not dry_run:
            result["status"] = "COMPLETED"
        logger.info("Telegram profile sync alias=%s mode=%s status=%s",
                    profile.alias, "dry-run" if dry_run else "apply", result["status"])
        return result

    @staticmethod
    def _http_transport(token: str, method: str, payload: Dict[str, object]):
        url = "https://api.telegram.org/bot%s/%s" % (token, method)
        encoded = parse.urlencode({
            key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
            for key, value in payload.items()
        }).encode("utf-8")
        try:
            with request.urlopen(request.Request(url, data=encoded), timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            raise RuntimeError("Telegram profile synchronization failed; details are hidden.")
