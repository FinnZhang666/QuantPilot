from abc import ABC, abstractmethod
from datetime import datetime

from app.core.enums import AdjustmentType, BarInterval
from app.historical.models import HistoryFetchResult


class HistoricalDataProvider(ABC):
    @abstractmethod
    def fetch_bars(
        self,
        symbol: str,
        interval: BarInterval,
        start_time: datetime,
        end_time: datetime,
        adjustment_type: AdjustmentType,
    ) -> HistoryFetchResult:
        raise NotImplementedError
