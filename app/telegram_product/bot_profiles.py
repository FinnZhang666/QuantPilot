"""Configuration-backed Telegram bot registry.

Tokens are resolved from Settings only. They are never stored in the registry file,
database, logs, sync results, or API responses.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import TelegramAdminRecord, TelegramBotProfileRecord


@dataclass(frozen=True)
class BotCommand:
    command: str
    description: str


@dataclass(frozen=True)
class BotMenuItem:
    label: str
    action: str


@dataclass(frozen=True)
class TelegramBotProfile:
    alias: str
    language: str
    display_name: str
    short_description: str
    description: str
    welcome: str
    commands: Tuple[BotCommand, ...]
    main_menu: Tuple[BotMenuItem, ...]
    token_setting: str
    fallback_token_settings: Tuple[str, ...]
    token: str
    enabled: bool
    profile_photo: str = "app/dashboard/static/branding/trade-companion-logo.png"

    @property
    def more_menu(self) -> Tuple[BotMenuItem, ...]:
        return (
            BotMenuItem("Help", "help"), BotMenuItem("Feedback", "feedback"),
            BotMenuItem("Updates", "updates"), BotMenuItem("Change Language", "language"),
            BotMenuItem("About", "about"), BotMenuItem("Watchlist", "watchlist"),
            BotMenuItem("Holdings", "holding"), BotMenuItem("History", "history"),
            BotMenuItem("Reviews", "review"),
        )

    @property
    def welcome_uses_image(self) -> bool:
        return False

    @property
    def purpose(self) -> str:
        return "trade_companion"

    @property
    def market_scope(self) -> str:
        return "US"

    def safe_summary(self) -> Dict[str, object]:
        return {
            "alias": self.alias,
            "language": self.language,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "lifecycle_state": "PRODUCTION" if self.enabled else "RESERVED",
            "token_configured": bool(self.token),
            "profile_photo": self.profile_photo,
            "avatar_sync": "MANUAL_REQUIRED",
        }


def _registry_path(settings: Settings, repository_root: Optional[Path] = None) -> Path:
    path = Path(settings.telegram_registry_path)
    if path.is_absolute():
        return path
    root = repository_root or Path(__file__).resolve().parents[2]
    return root / path


def load_bot_profiles(
    settings: Settings, repository_root: Optional[Path] = None,
) -> List[TelegramBotProfile]:
    path = _registry_path(settings, repository_root)
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles = []
    aliases = set()
    raw_items = data.get("bots", [])
    templates = {str(item["alias"]): item for item in raw_items}
    for source in raw_items:
        item = dict(source)
        template_alias = item.get("template")
        if template_alias:
            inherited = dict(templates[str(template_alias)])
            inherited.update(item)
            item = inherited
        alias = str(item["alias"]).strip()
        if alias in aliases:
            raise ValueError("Duplicate Telegram bot alias: %s" % alias)
        aliases.add(alias)
        token_setting = str(item["token_setting"])
        fallback_items = list(item.get("fallback_token_settings") or [])
        fallback = item.get("fallback_token_setting")
        if fallback:
            fallback_items.insert(0, str(fallback))
        token = str(getattr(settings, token_setting, "") or "")
        for fallback_setting in fallback_items:
            if not token:
                token = str(getattr(settings, str(fallback_setting), "") or "")
        profiles.append(TelegramBotProfile(
            alias=alias,
            language=str(item["language"]),
            display_name=str(item["name"]),
            short_description=str(item["about"]),
            description=str(item["description"]),
            welcome=str(item["welcome_template"]),
            commands=tuple(BotCommand(**command) for command in item.get("commands", [])),
            main_menu=tuple(BotMenuItem(**menu) for menu in item.get("menu", [])),
            token_setting=token_setting,
            fallback_token_settings=tuple(str(value) for value in fallback_items),
            token=token,
            enabled=bool(item.get("runtime_enabled", False)),
        ))
    return profiles


def validate_profile(profile: TelegramBotProfile, repository_root: Path) -> List[str]:
    errors = []
    if profile.language not in {"zh-CN", "en-US", "multi"}:
        errors.append("invalid_language")
    if len(profile.short_description) > 120:
        errors.append("short_description_too_long")
    if len(profile.description) > 512:
        errors.append("description_too_long")
    if len(profile.welcome) > 4096:
        errors.append("welcome_too_long")
    if len(profile.main_menu) != 4:
        errors.append("invalid_main_menu")
    if any(not item.command.islower() or len(item.command) > 32 for item in profile.commands):
        errors.append("invalid_command")
    if not (repository_root / profile.profile_photo).is_file():
        errors.append("profile_photo_missing")
    return errors


def synchronize_registry(db: Session, settings: Settings) -> List[TelegramBotProfile]:
    profiles = load_bot_profiles(settings)
    for profile in profiles:
        row = db.scalar(select(TelegramBotProfileRecord).where(
            TelegramBotProfileRecord.alias == profile.alias,
        ))
        if row is None:
            row = TelegramBotProfileRecord(alias=profile.alias)
            db.add(row)
        row.language = profile.language
        row.display_name = profile.display_name
        row.about = profile.short_description
        row.description = profile.description
        row.commands_json = [item.__dict__ for item in profile.commands]
        row.menu_json = [item.__dict__ for item in profile.main_menu]
        row.welcome_template = profile.welcome
        row.token_env_key = profile.token_setting
        row.runtime_enabled = profile.enabled
        if not profile.enabled:
            row.runtime_status = "RESERVED"
    for username, role in (("ADHD360", "SUPER_ADMIN"), ("Kevinchou8", "ADMIN")):
        admin = db.scalar(select(TelegramAdminRecord).where(
            TelegramAdminRecord.username == username,
        ))
        if admin is None:
            db.add(TelegramAdminRecord(
                username=username, display_name="@" + username, role=role, enabled=True,
            ))
    db.commit()
    return profiles
