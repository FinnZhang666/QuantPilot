from abc import ABC, abstractmethod
from typing import Any


class FeatureCalculator(ABC):
    @abstractmethod
    async def calculate(self, market_data: Any) -> Any:
        raise NotImplementedError
