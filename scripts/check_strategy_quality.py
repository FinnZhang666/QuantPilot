#!/usr/bin/env python3
from pathlib import Path
import shutil

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.strategy.quality import StrategyQualityService


def main() -> int:
    settings = get_settings()
    with get_session_factory()() as db:
        report = StrategyQualityService().inspect(db)
    db_path = settings.database_url.replace("sqlite:///", "")
    size = Path(db_path).stat().st_size / (1024 ** 3) if Path(db_path).exists() else 0
    free = shutil.disk_usage(".").free / (1024 ** 3)
    print("Strategy质量检查")
    for key, value in report.items():
        print("%s：%s" % (key, value))
    print("数据库大小GB：%.3f" % size)
    print("磁盘剩余GB：%.3f" % free)
    return 0 if not report["issues"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
