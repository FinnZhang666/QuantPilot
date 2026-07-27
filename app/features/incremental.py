from typing import Iterable, Optional

from app.features.pipeline import FeatureCalculationService


class RealtimeFeatureUpdater:
    """由闭合K线事件或手工任务调用；不运行于Moomoo回调线程。"""

    def __init__(self, service: FeatureCalculationService):
        self.service = service

    def update_closed_bar(self, symbol: str, feature_names: Optional[Iterable[str]] = None):
        return self.service.calculate_realtime_closed(symbol, feature_names)
