"""Read-only restore readiness drill for a SQLite backup.

This script never copies, opens for write, restores, or replaces a database.
"""

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

from app.core.config import get_settings


def database_path() -> Path:
    value = get_settings().database_url
    prefix = "sqlite:///"
    if not value.startswith(prefix):
        raise ValueError("Restore readiness currently supports SQLite only.")
    return Path(value[len(prefix):]).resolve()


def inspect_database(path: Path) -> dict:
    result = {"path": str(path), "exists": path.is_file()}
    if not result["exists"]:
        return result
    result["size_bytes"] = path.stat().st_size
    with path.open("rb") as stream:
        result["sqlite_header_valid"] = stream.read(16) == b"SQLite format 3\x00"
    uri = "file:%s?mode=ro&immutable=1" % path.as_posix()
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version",
        ).fetchone()
        result["alembic_revision"] = revision[0] if revision else None
        result["table_count"] = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'",
        ).fetchone()[0]
        result["sqlite_version"] = connection.execute(
            "SELECT sqlite_version()",
        ).fetchone()[0]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only SQLite restore readiness drill")
    parser.add_argument("--backup", required=True, type=Path)
    args = parser.parse_args()
    formal = database_path()
    backup = args.backup.resolve()
    formal_result = inspect_database(formal)
    backup_result = inspect_database(backup)
    usage = shutil.disk_usage(formal.parent)
    required = int(backup_result.get("size_bytes") or 0) + 20 * 1024 ** 3
    reasons = []
    if not backup_result.get("exists"):
        reasons.append("backup_missing")
    if not backup_result.get("sqlite_header_valid"):
        reasons.append("invalid_sqlite_header")
    if backup_result.get("alembic_revision") != formal_result.get("alembic_revision"):
        reasons.append("migration_revision_mismatch")
    if usage.free < required:
        reasons.append("insufficient_restore_workspace")
    result = {
        "status": "READY" if not reasons else "BLOCKED",
        "mode": "READ_ONLY_DRY_RUN",
        "formal": formal_result,
        "backup": backup_result,
        "target_free_bytes": usage.free,
        "minimum_required_bytes": required,
        "blockers": reasons,
        "copy_performed": False,
        "restore_performed": False,
        "formal_database_modified": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
