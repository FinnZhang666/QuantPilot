import os
import time

import pytest

from app.core.config import get_settings
from app.realtime.factory import build_realtime_manager


@pytest.mark.live_moomoo
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_MOOMOO") != "true",
    reason="仅在用户已登录OpenD并显式设置RUN_LIVE_MOOMOO=true时运行",
)
def test_live_realtime_subscription_read_only():
    manager = build_realtime_manager(get_settings(), ["US.QQQ", "US.SOXL"])
    try:
        result = manager.start()
        assert "US.QQQ" in result.successful
        time.sleep(3)
    finally:
        manager.stop()
    assert manager.error_count == 0
