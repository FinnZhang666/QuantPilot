#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import get_session_factory
from app.features.registry import FeatureRegistry
from app.features.repository import FeatureRepository


def main() -> int:
    db = get_session_factory()()
    try:
        count = FeatureRepository(db).initialize_definitions(FeatureRegistry.defaults().list())
        print("特征定义初始化完成：%s项（幂等）" % count)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

