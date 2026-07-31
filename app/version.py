import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

PRODUCT = "Trade Companion"
VERSION = "0.9.0-beta"
SPRINT = "29"
MIGRATION = "0014"
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
    if db is not None:
        try:
            database_version = str(db.execute(text("select sqlite_version()")).scalar())
        except Exception:
            database_version = "unavailable"
    return {
        "product": PRODUCT, "version": VERSION, "sprint": SPRINT,
        "commit": _git_value("rev-parse", "--short", "HEAD"),
        "migration": MIGRATION, "build_time": BUILD_TIME,
        "python": platform.python_version(), "database_version": database_version,
        "git_branch": _git_value("branch", "--show-current"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
