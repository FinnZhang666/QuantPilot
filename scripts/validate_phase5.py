"""Safe Phase 5 validation; prints state only, never local secret values."""

import sqlite3

from app.core.config import get_settings
from app.telegram_product.bot_profiles import load_bot_profiles


def main():
    settings = get_settings()
    path = settings.database_url.removeprefix("sqlite:///")
    connection = sqlite3.connect(path)
    try:
        head = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        tables = connection.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type = 'table' AND name LIKE 'telegram_%'"
        ).fetchone()[0]
        phase5_integrity = {}
        for table in (
            "telegram_bot_profiles", "telegram_runtime_users", "telegram_admins",
            "telegram_feedback", "telegram_runtime_message_logs",
            "telegram_profile_sync_logs", "telegram_ai_invocations",
        ):
            phase5_integrity[table] = connection.execute(
                "PRAGMA integrity_check('%s')" % table
            ).fetchone()[0]
        admins = [
            {"username": row[0], "bound": bool(row[1]), "enabled": bool(row[2])}
            for row in connection.execute(
                "SELECT username, telegram_user_id, enabled FROM telegram_admins ORDER BY id"
            ).fetchall()
        ]
        runtime_counts = {
            "users": connection.execute("SELECT count(*) FROM telegram_runtime_users").fetchone()[0],
            "messages": connection.execute("SELECT count(*) FROM telegram_runtime_message_logs").fetchone()[0],
            "feedback": connection.execute("SELECT count(*) FROM telegram_feedback").fetchone()[0],
            "ai_invocations": connection.execute("SELECT count(*) FROM telegram_ai_invocations").fetchone()[0],
        }
        latest_error_row = connection.execute(
            "SELECT error_code, error_message FROM telegram_runtime_message_logs "
            "WHERE status = 'FAILED' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        latest_error = None if latest_error_row is None else {
            "error_code": latest_error_row[0], "error_message": latest_error_row[1],
        }
    finally:
        connection.close()
    profiles = load_bot_profiles(settings)
    forbidden_copy = ("marketing bot", "dating", "crypto signal", "adhd product")
    profile_audit = {}
    for profile in profiles:
        public_copy = " ".join((
            profile.display_name, profile.short_description, profile.description,
            profile.welcome, " ".join(item.description for item in profile.commands),
        )).lower()
        profile_audit[profile.alias] = {
            "brand": profile.display_name == "Trade Companion",
            "welcome": "Trade Companion" in profile.welcome,
            "language": profile.language,
            "menu_items": len(profile.main_menu),
            "runtime_enabled": profile.enabled,
            "token_configured": bool(profile.token),
            "old_marketing_content": any(term in public_copy for term in forbidden_copy),
        }
    print({
        "phase5_integrity": phase5_integrity,
        "head": head,
        "telegram_tables": tables,
        "registry_bots": len(profiles),
        "enabled_bots": sum(item.enabled for item in profiles),
        "configured_tokens": sum(bool(item.token) for item in profiles),
        "runnable_bots": sum(item.enabled and bool(item.token) for item in profiles),
        "profile_audit": profile_audit,
        "gemini_key_configured": bool(
            settings.ai_companion_api_key or settings.gemini_api_key
        ),
        "admins": admins,
        "runtime_counts": runtime_counts,
        "latest_error": latest_error,
        "real_order_calls": 0,
        "opend_trade_calls": 0,
    })


if __name__ == "__main__":
    main()
