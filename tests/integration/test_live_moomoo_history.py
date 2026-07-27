import os
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.core.enums import AdjustmentType, BarInterval
from app.historical.factory import build_history_provider


@pytest.mark.live_moomoo
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_MOOMOO") != "true",
    reason="仅在用户已登录OpenD并显式设置RUN_LIVE_MOOMOO=true时运行",
)
def test_live_qqq_history_read_only():
    settings = get_settings()
    result = build_history_provider(settings).fetch_bars(
        "US.QQQ",
        BarInterval.DAY_1,
        datetime.now(timezone.utc) - timedelta(days=10),
        datetime.now(timezone.utc),
        AdjustmentType.FORWARD,
    )
    assert result.success
    assert result.bars
