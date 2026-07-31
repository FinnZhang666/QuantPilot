import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

PRODUCT = "Trade Companion"
VERSION = "1.0.0-rc1"
SPRINT = "39"
BUILD_TIME = datetime.now(timezone.utc).isoformat()


def _git_value(*args):
    try:
        return subprocess.check_output(
            ["git"] + list(args), cwd=Path(__file__).resolve().parents[1],
            text=True, stderr=subprocess.DEVNULL, timeout=2,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def version_info(db=None):
    database_version = "unknown"
    migration = "unknown"
    if db is not None:
        try:
            database_version = str(db.execute(text("select sqlite_version()")).scalar())
        except Exception:
            database_version = "unavailable"
        try:
            migration = str(db.execute(text("select version_num from alembic_version")).scalar())
        except Exception:
            migration = "unknown"
    return {
        "product": PRODUCT, "version": VERSION, "sprint": SPRINT,
        "commit": _git_value("rev-parse", "--short", "HEAD"),
        "migration": migration, "build_time": BUILD_TIME,
        "python": platform.python_version(), "database_version": database_version,
        "git_branch": _git_value("branch", "--show-current"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
