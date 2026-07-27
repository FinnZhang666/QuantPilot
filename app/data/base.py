from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, List


class DataProvider(ABC):
    @abstractmethod
    async def get_quote(self, symbol: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def get_history(self, symbol: str, start: datetime, end: datetime, interval: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, symbols: List[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self, symbols: List[str]) -> None:
        raise NotImplementedError
