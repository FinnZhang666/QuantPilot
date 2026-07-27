from abc import ABC, abstractmethod
from typing import Any


class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, message: str) -> Any:
        raise NotImplementedError
